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
import zlib
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


def run_corpus(*, allow_single_judge: bool = False) -> pd.DataFrame:
    """LEGACY single-judge corpus run. Superseded by `run_corpus_consensus`.

    Kept because `predict()` and the tests exercise the dispatcher, but it must not be reachable by
    accident: it writes the same OUT_PARQUET with one unchecked opinion per job, which would silently
    downgrade every consensus label. Pass allow_single_judge=True to acknowledge that.
    """
    if not allow_single_judge:
        raise RuntimeError(
            "run_corpus() is the legacy single-judge path and overwrites the consensus labels in "
            f"{OUT_PARQUET.name}. Use run_corpus_consensus() (python -m pipeline label), or pass "
            "allow_single_judge=True if you really mean it.")
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


# =====================================================================================
# CONSENSUS voting (v3). Each LLM-tier job is judged by 2+ DISTINCT judges; agreement =
# confidence, disagreement escalates to a 3rd judge (majority). Replaces the single-model +
# human-review path — no manual labeling. Failover is implicit: a judge that errors/exhausts is
# skipped and the next judge in the per-job rotation votes instead.
# =====================================================================================

# Consensus judge pool, best-first; the tail entries act as arbiters. Deliberately NOT every provider
# with a key: `groq8b` is excluded because it is the outlier judge (OTHER rate 61% vs 75-77% for
# cerebras/mistral on the same cached corpus) — i.e. it is the one most willing to file a generic
# business role under a data family, and it used to decide the most jobs. `ninerouter`/`sambanova` are
# excluded for latency/reliability (they stalled jobs near the client timeout). Fewer, better,
# less-correlated judges beat more judges.
#
# Order is by SUSTAINED THROUGHPUT, not model size: `_consensus_one` uses the leading len-2 entries as
# first-voters and the last two as arbiters, so a slow judge in a leading slot throttles every job that
# rotates onto it (cerebras at 13s/call caps a quarter of the corpus at ~4.6 jobs/min). groq-70b and
# github gpt-4o-mini are the fast pair; cerebras/mistral are strong but slow, so they only arbitrate
# genuine disagreements. qwen/gemini stay in the list even when their daily quota is gone: their CACHED
# votes still count toward a quorum for free, and a quota-dead judge is skipped via the `dead` registry.
JUDGE_POOL = ["groq", "github", "cloudflare", "qwen", "gemini", "cerebras", "mistral"]


def _available_judges() -> list[str]:
    """Judge keys whose API key is present in .env (preserves JUDGES order)."""
    sec = get_secrets()
    from pipeline.dataset.llm_clients import JUDGES as _J
    return [k for k, j in _J.items() if getattr(sec, j.key_env, None)]


def _decide_votes(votes: list[dict], job: dict) -> dict:
    """Aggregate collected votes into one labeled result."""
    if not votes:
        return _result(job, "OTHER", 0.0, "failed", [], "all judges failed", "manual_review")
    tally = Counter(v["job_family"] for v in votes)
    fam, n_agree = tally.most_common(1)[0]
    n = len(votes)
    agree = [v for v in votes if v["job_family"] == fam]
    conf = sum(v["confidence"] for v in agree) / len(agree)
    judge_keys = sorted({llm_judge.provider_key_for(v["judge"]) for v in votes})
    if n_agree >= 2:                                   # consensus / majority
        # Keep the judges' own mean confidence. The previous `conf * (0.9 + 0.1*n_agree)` capped at 0.99
        # pinned 76% of two-vote rows to exactly 0.99, so the "confidence distribution" KPI described the
        # formula rather than the labels. Agreement strength belongs in its own columns, not smuggled
        # into a score that is already a mix of incommensurable scales.
        review = "resolved"
        method = "vote:" + "+".join(judge_keys)
    elif n == 1:
        # Only one judge ever answered (the others were exhausted/erroring). This job did NOT get the
        # 2-vote standard, so label the method `single:` — never silently pass it off as a vote, and
        # send it to review unless the lone judge was confident.
        review = "resolved" if votes[0]["confidence"] >= 0.6 else "manual_review"
        method = "single:" + "+".join(judge_keys)
    else:                                              # every judge disagreed (rare)
        # No majority. If the disputed families all sit inside ONE taxonomy domain, the judges DO agree
        # at domain level (a posting titled just "Analyst" drawing BUSINESS_ANALYST / DATA_ANALYST /
        # RISK_FRAUD_ANALYST is unanimously "Analytics") — record that instead of pretending to a family.
        # Such rows are excluded from family tables but counted in `gold_domain_share`. Otherwise the
        # dispute crosses domains (usually because one judge said OTHER, i.e. "not a data job at all",
        # which has no common ancestor with any family) and only stage-2 `refine` can settle it.
        doms = {meta(v["job_family"]).get("domain") for v in votes}
        best = max(votes, key=lambda v: v["confidence"])
        fam, conf = best["job_family"], best["confidence"] * 0.7
        if len(doms) == 1 and None not in doms and "OTHER" not in {v["job_family"] for v in votes}:
            review, method = "domain_only", "domain-consensus:" + "+".join(judge_keys)
        else:
            review, method = "manual_review", "split:" + "+".join(judge_keys)
    reasoning = next((v["reasoning"] for v in votes if v["job_family"] == fam), "")
    return _result(job, fam, conf, method, votes, reasoning, review)


def _vote_once(judge_key: str, job: dict, dead: set | None = None) -> dict | None:
    """One vote: CACHE FIRST (no throttle), then a single live attempt. Returns None on any failure so
    the caller fails over to the next judge immediately.

    Two correctness/speed guards:
      * the cache probe happens BEFORE `_throttle`, so a cached vote costs ~0ms instead of waiting on
        that judge's global rate lock (this is what made resumed runs take hours);
      * `dead` is a shared registry of providers that returned a daily-quota 429 — once a judge is in
        it, every worker skips it for the rest of the run instead of re-discovering it job by job.
    """
    from pipeline.dataset.llm_clients import _throttle
    hit = llm_judge.cached_vote(judge_key, job)
    if hit is not None:
        return hit
    if dead is not None and judge_key in dead:
        return None
    try:
        _throttle(judge_key)
        return llm_judge.classify_once(judge_key, job)
    except llm_judge.RateLimited as rl:
        if dead is not None and rl.reset_seconds > EXHAUST_RESET:
            dead.add(judge_key)
            log.warning("judge %s EXHAUSTED (reset ~%.0fs) — skipped for the rest of this run",
                        judge_key, rl.reset_seconds)
        return None
    except Exception:  # noqa: BLE001  (network / JSON / bad-code → drop this judge's vote)
        return None


def _consensus_one(job: dict, judges: list[str], dead: set | None = None) -> dict:
    """Collect distinct-judge votes for one job: ALWAYS seek >= 2 votes; a 3rd only breaks a tie.

    Uniform standard on purpose. The earlier version accepted a single vote whenever the label was a
    confident non-{OTHER, BUSINESS_ANALYST} family — which held BA/OTHER to a harsher evidence bar
    than the data families, and so quietly pushed borderline postings INTO data families: the mirror
    image of the contamination it was meant to fix. Measured evidence also killed its premise: among
    jobs where two judges disagreed, 36/66 had BOTH judges self-reporting confidence >= 0.85, so LLM
    self-confidence is not calibrated well enough to license a single vote.

    `judges` is pre-sorted best-first; the tail acts as arbiters. Rotation is seeded per job so load
    spreads across judges, using crc32 — NOT `hash()`, which is salted per process and made judge
    assignment irreproducible between runs.
    """
    k = len(judges)
    fast = max(2, k - 2)                                  # all but the 2 slowest are first-voters
    seed = zlib.crc32((job.get("content_hash") or job.get("job_id") or "").encode()) % fast
    order = [judges[(seed + i) % fast] for i in range(fast)] + judges[fast:]
    votes: list[dict] = []
    for jk in order:
        rec = _vote_once(jk, job, dead)
        if rec is None:
            continue                                    # judge failed/exhausted → failover to next
        votes.append(rec)
        if len(votes) == 2 and votes[0]["job_family"] == votes[1]["job_family"]:
            break                                       # two independent judges agree → done
        if len(votes) >= 3:
            break                                       # arbiter cast → decide by majority
    return _decide_votes(votes, job)


def run_corpus_consensus(max_workers: int = 10) -> pd.DataFrame:
    df = pd.read_parquet(_io.TEXT_DIR / "jobs_text.parquet")
    jobs = df.to_dict("records")
    embed_match._prototypes(); embed_match._job_vectors()  # warm once
    n = len(jobs)
    have = set(_available_judges())
    judges = [k for k in JUDGE_POOL if k in have]       # JUDGE_POOL order = best-first
    if len(judges) < 3:
        # `fast = max(2, k-2)` leaves judges[fast:] empty below 3, i.e. no arbiter for a disagreement.
        # Two judges can only ever agree or deadlock, so require a third before claiming a tiebreak.
        raise RuntimeError(
            f"consensus needs >=3 judges (2 voters + 1 arbiter) with keys in .env; have {judges}")
    dead: set[str] = set()                              # providers exhausted during THIS run
    print(f"\n{'='*64}\nJOB FAMILY ENGINE (CONSENSUS v4) — {n} jobs\n"
          f"judges ({len(judges)}, best-first): {judges}\n{'='*64}", flush=True)

    # Pass 1: local tiers (rule + embedding) — unchanged, free.
    results, remainder = [], []
    for job in jobs:
        r = _tier12(job)
        (results.append(r) if r else remainder.append(job))
    print(f"  tier1+tier2 resolved {len(results)}/{n}; LLM remainder {len(remainder)}", flush=True)

    # Pass 2: consensus vote per UNIQUE content_hash, then fan out to duplicate postings.
    if remainder:
        by_hash: dict = {}
        for job in remainder:
            by_hash.setdefault(job["content_hash"], []).append(job)
        reps = [grp[0] for grp in by_hash.values()]
        print(f"  consensus on {len(reps)} unique (from {len(remainder)}); >=2 votes each", flush=True)
        rep_results: list = []
        done, lock = [0], threading.Lock()

        def work(job: dict) -> None:
            try:
                r = _consensus_one(job, judges, dead)
            except Exception as exc:  # noqa: BLE001
                r = _result(job, "OTHER", 0.0, "failed", [],
                            f"consensus error: {str(exc)[:80]}", "manual_review")
            with lock:
                rep_results.append(r)
                done[0] += 1
                if done[0] % 25 == 0 or done[0] == len(reps):
                    print(f"    labeled {done[0]}/{len(reps)}", flush=True)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(work, reps))

        rep_by_id = {r["job_id"]: r for r in rep_results}
        for grp in by_hash.values():
            rep = rep_by_id[grp[0]["job_id"]]
            for job in grp:
                results.append(rep if job["job_id"] == rep["job_id"] else {**rep, "job_id": job["job_id"]})

    out = pd.DataFrame(results)
    _io.write_parquet(out, OUT_PARQUET, schema_version="job_family/1", produced_by="job_family_engine")
    print(f"\nmethod: {dict(Counter(out['labeling_method']))}")
    print(f"review: {dict(Counter(out['review_status']))}")
    print(f"families: {dict(Counter(out['job_family']).most_common())}")
    print(f"-> {OUT_PARQUET}")
    return out
