"""Cascade: rule → embedding → LLM + confidence + review.

LLM tier uses a DYNAMIC DISPATCHER with FAILOVER (not a static partition). tier-1/tier-2 run
locally first; the LLM remainder goes into one shared queue drained by a worker pool. For each job a
worker picks the provider that is free soonest (respecting each provider's measured req/min and daily
cap) and makes ONE call:
  * success         → cache + record (provider's daily counter ++)
  * 429, short reset → cool that provider briefly, RE-QUEUE the job (another provider takes it now)
  * 429, long reset  → mark that provider EXHAUSTED for this run, RE-QUEUE (never wait out a daily cap)
  * all exhausted    → remaining jobs become manual_review (resumable: rerun after quota resets)
So one provider hitting its limit can never stall the others — load flows to whoever has capacity.
Fully resumable: any job already cached by ANY judge is reused instantly (no quota spent).

Measured free-tier req/min · daily cap: groq-8b ~15·14.4k · gemini 15·1.5k · groq-70b ~24·1k ·
cerebras 5·2.4k · mistral ~3 · openrouter-qwen ~2·50. Combined ≈ 60/min; aggregate daily caps far
exceed the corpus, and groq-8b + gemini alone can carry the whole tail if the others exhaust.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pandas as pd

from pipeline.dataset import _io
from pipeline.dataset.llm_clients import JUDGES
from pipeline.utils.config import DATA_DIR, get_secrets

from . import embed_match, llm_judge, rules
from .taxonomy import TAXONOMY_VERSION, meta

log = logging.getLogger("job_family_engine.engine")
OUT_PARQUET = DATA_DIR / "labeling" / "job_family.parquet"
RULE_MIN_CONF = 0.9

# (judge_key, capacity ≈ req/min, daily cap). Order = preference when equally free.
PROVIDERS = [
    ("groq8b", 15, 14000),   # workhorse: fast + huge daily headroom
    ("gemini", 15, 1400),    # strong base: free 15 rpm / 1500 rpd
    ("groq", 24, 950),       # fastest rpm but low daily (1000/day)
    ("cerebras", 5, 2300),   # strong model, modest rpm, ok daily (2400/day)
    ("mistral", 3, 300),     # slow free tier → minor contributor
    ("qwen", 2, 45),         # openrouter free ~50/day → bonus only
]
EXHAUST_RESET = 90.0   # a 429 whose reset exceeds this ⇒ treat provider as done for THIS run
MAX_ATTEMPTS = 8       # re-routes per job across providers before giving up → manual_review
IDLE_TIMEOUT = 300.0   # backstop: if no job is finalized/re-queued for this long while jobs remain,
                       # abort the idle workers (stop spinning). In-flight calls are separately bounded
                       # by the per-client 60s network timeout, so the pool still drains.


@dataclass
class _PState:
    key: str
    min_interval: float        # seconds between calls (= 60/rpm)
    cap: int                   # daily request cap
    next_free: float = 0.0     # monotonic time the next call may start (rate spacing)
    cooling_until: float = 0.0 # monotonic time a short 429 cooldown ends
    used: int = 0              # successful calls this run
    exhausted: bool = False    # daily cap hit / long cooldown → skip for this run

    def avail(self, now: float) -> float:
        return max(self.next_free, self.cooling_until, now)


def _result(job, code, conf, method, votes, reasoning, review) -> dict:
    m = meta(code)
    return {
        "job_id": job["job_id"], "job_family": code,
        "domain": m.get("domain"), "subdomain": m.get("subdomain"),
        "confidence_score": round(float(conf), 3), "labeling_method": method,
        "llm_votes": json.dumps([{"judge": v["judge"], "job_family": v["job_family"],
                                  "confidence": v["confidence"]} for v in (votes or [])],
                                ensure_ascii=False),
        "reasoning": (reasoning or "")[:300], "review_status": review,
        "taxonomy_version": TAXONOMY_VERSION,
    }


def _tier12(job: dict) -> dict | None:
    """Local, free tiers. Returns a result or None (→ needs LLM)."""
    c, conf, alias = rules.tier1(job.get("title"))
    if c and conf >= RULE_MIN_CONF:
        return _result(job, c, conf, "rule", None, f"title alias '{alias}'", "resolved")
    c2, score, margin = embed_match.tier2(job.get("job_id"), job.get("role_view"))
    if c2:
        return _result(job, c2, score, "embedding", None,
                       f"embed sim {score:.2f} (margin {margin:.2f})", "resolved")
    return None


def _llm_result(job: dict, rec: dict, method: str) -> dict:
    review = "resolved" if rec["confidence"] >= 0.6 else "manual_review"
    return _result(job, rec["job_family"], rec["confidence"], method, [rec], rec["reasoning"], review)


def _tier3(job: dict, provider: str = "groq8b") -> dict:
    """Single-job LLM path (used by predict()). Self-contained retry in classify_one."""
    rec = llm_judge.classify_one(provider, job)
    if not rec:
        return _result(job, "OTHER", 0.0, "failed", [], f"{provider} failed", "manual_review")
    return _llm_result(job, rec, f"llm:{provider}")


def predict(job: dict, llm_provider: str = "groq8b") -> dict:
    return _tier12(job) or _tier3(job, llm_provider)


def _active_states() -> list[_PState]:
    """Provider states for those whose API key is present (preserves PROVIDERS order)."""
    sec = get_secrets()
    out = []
    for key, rpm, cap in PROVIDERS:
        env = JUDGES[key].key_env
        if getattr(sec, env, None):
            out.append(_PState(key=key, min_interval=60.0 / max(rpm, 1), cap=cap))
        else:
            log.warning("provider %s skipped (missing %s)", key, env)
    return out


def _label_remainder(remainder: list[dict], results: list[dict], n: int) -> None:
    """Dynamic dispatch with failover over the LLM remainder. Appends to `results` in place."""
    states = _active_states()
    if not states:
        raise RuntimeError("no LLM provider keys present in .env — cannot run Tier-3")
    print(f"  providers: {[s.key for s in states]}", flush=True)

    queue: deque[tuple[dict, int]] = deque((job, 0) for job in remainder)
    pending = [len(remainder)]
    abort = [False]                       # tripped by the idle backstop → all workers stop
    last_progress = [time.monotonic()]    # monotonic time of the last finalize/requeue
    q_lock, disp_lock, res_lock = threading.Lock(), threading.Lock(), threading.Lock()

    def finalize(r: dict) -> None:
        with res_lock:
            results.append(r)
        with q_lock:
            pending[0] -= 1
            last_progress[0] = time.monotonic()
            d = n - pending[0]
        try:   # progress I/O must NEVER raise after the commit above — else the worker's outer
            if d % 50 == 0 or d == n:   # except would re-finalize the same job (double-count).
                with disp_lock:
                    use = {s.key: s.used for s in states if s.used}
                print(f"  labeled {d}/{n}  used={use}", flush=True)
        except Exception:  # noqa: BLE001
            pass

    def requeue(job: dict, attempts: int) -> None:
        with q_lock:
            queue.append((job, attempts))
            last_progress[0] = time.monotonic()

    def _retry_or_drop(job: dict, attempts: int, why: str) -> None:
        if attempts < MAX_ATTEMPTS:
            requeue(job, attempts)
        else:
            finalize(_result(job, "OTHER", 0.0, "failed", [], why, "manual_review"))

    def select(now: float):
        """Pick + reserve the provider free soonest. Returns (state, wait) or (None, None)."""
        with disp_lock:
            cands = [s for s in states if not s.exhausted and s.used < s.cap]
            if not cands:
                return None, None
            s = min(cands, key=lambda s: s.avail(now))
            wait = max(0.0, s.avail(now) - now)
            s.next_free = s.avail(now) + s.min_interval   # reserve this slot
            return s, wait

    def on_429(s: _PState, reset: float) -> None:
        with disp_lock:
            if reset > EXHAUST_RESET:
                if not s.exhausted:
                    s.exhausted = True
                    log.warning("provider %s EXHAUSTED (reset ~%.0fs) — rerouting its jobs", s.key, reset)
            else:
                s.cooling_until = max(s.cooling_until, time.monotonic() + reset)

    def _process(job: dict, attempts: int) -> None:
        """Label one job: finalize on success/exhaust, or re-queue on a recoverable 429/error.
        Calls finalize OR requeue exactly once (the outer worker guards anything that escapes)."""
        hit = llm_judge.cached_any(job)   # resume / cross-provider reuse — no quota spent
        if hit:
            prov = llm_judge.provider_key_for(hit.get("judge", "cache"))  # same value space as live
            finalize(_llm_result(job, hit, f"llm:{prov}"))
            return
        s, wait = select(time.monotonic())
        if s is None:
            finalize(_result(job, "OTHER", 0.0, "failed", [],
                             "all providers exhausted (rerun after quota reset)", "manual_review"))
            return
        if wait > 0:
            time.sleep(min(wait, EXHAUST_RESET))   # cover the full cooldown ceiling (≤90s), so we
            #                                        don't retry a still-cooling provider too early
        try:
            rec = llm_judge.classify_once(s.key, job)
        except llm_judge.RateLimited as rl:
            on_429(s, rl.reset_seconds)
            _retry_or_drop(job, attempts + 1, "rate-limited (max retries)")
            return
        except Exception as exc:  # noqa: BLE001  (network/JSON/etc → re-route, never lose the job)
            log.warning("%s job %s: %s", s.key, job.get("job_id"), str(exc)[:140])
            _retry_or_drop(job, attempts + 1, f"error: {str(exc)[:80]}")
            return
        with disp_lock:
            s.used += 1
            if s.used >= s.cap:
                s.exhausted = True
        finalize(_llm_result(job, rec, f"llm:{s.key}"))

    def worker() -> None:
        while True:
            if abort[0]:
                return
            with q_lock:
                if pending[0] == 0:
                    return
                item = queue.popleft() if queue else None
            if item is None:
                # queue momentarily empty (re-queues in flight). Yield; trip a backstop if the whole
                # pool has made no progress for too long, so a stuck job can never hang the run.
                with q_lock:
                    stalled = pending[0] > 0 and (time.monotonic() - last_progress[0]) > IDLE_TIMEOUT
                if stalled:
                    log.error("dispatcher made no progress for %.0fs with %d jobs left — aborting "
                              "(rerun resumes from cache)", IDLE_TIMEOUT, pending[0])
                    abort[0] = True
                    return
                time.sleep(0.2)
                continue
            job, attempts = item
            try:
                _process(job, attempts)
            except Exception as exc:  # noqa: BLE001  (last-resort: a popped job is NEVER lost)
                log.error("dispatch error job %s: %s", job.get("job_id"), str(exc)[:140])
                finalize(_result(job, "OTHER", 0.0, "failed", [],
                                 f"engine error: {str(exc)[:80]}", "manual_review"))

    n_workers = max(3, min(12, len(states) * 2))
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        list(ex.map(lambda _: worker(), range(n_workers)))

    # Drain anything still queued (only possible if the idle backstop tripped) so every remainder
    # job has a row → coverage stays 100% and `integrate` never sees a gap. Re-runs resume from cache.
    while queue:
        job, _ = queue.popleft()
        results.append(_result(job, "OTHER", 0.0, "failed", [], "aborted (stuck) — rerun", "manual_review"))

    with disp_lock:
        print(f"  provider usage: { {s.key: s.used for s in states} }"
              f"  exhausted: {[s.key for s in states if s.exhausted]}", flush=True)


def run_corpus() -> pd.DataFrame:
    df = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")
    jobs = df.to_dict("records")
    embed_match._prototypes(); embed_match._job_vectors()  # warm once
    n = len(jobs)
    print(f"\n{'='*64}\nJOB FAMILY ENGINE — {n} jobs (rule→embed→LLM, dynamic failover)\n{'='*64}", flush=True)

    # Pass 1: local tiers (rule + embedding)
    results, remainder = [], []
    for job in jobs:
        r = _tier12(job)
        (results.append(r) if r else remainder.append(job))
    print(f"  tier1+tier2 resolved {len(results)}/{n}; LLM remainder {len(remainder)}", flush=True)

    # Pass 2: dynamic dispatch with failover — one LLM call per UNIQUE content_hash (duplicate
    # postings share an identical label), then fan each representative's label out to its siblings.
    if remainder:
        by_hash: dict = {}
        for job in remainder:
            by_hash.setdefault(job["content_hash"], []).append(job)
        reps = [grp[0] for grp in by_hash.values()]
        if len(reps) < len(remainder):
            print(f"  (deduped {len(remainder)} → {len(reps)} unique content_hash)", flush=True)
        rep_results: list = []
        _label_remainder(reps, rep_results, len(reps))
        rep_hash = {grp[0]["job_id"]: h for h, grp in by_hash.items()}
        for r in rep_results:
            for job in by_hash.get(rep_hash.get(r["job_id"]), []):
                results.append(r if job["job_id"] == r["job_id"] else {**r, "job_id": job["job_id"]})

    out = pd.DataFrame(results)
    _io.write_parquet(out, OUT_PARQUET, schema_version="job_family/1", produced_by="job_family_engine")
    print(f"\nmethod: {dict(Counter(out['labeling_method']))}")
    print(f"review: {dict(Counter(out['review_status']))}")
    print(f"families: {dict(Counter(out['job_family']).most_common())}")
    print(f"-> {OUT_PARQUET}")
    return out
