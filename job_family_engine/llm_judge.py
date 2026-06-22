"""Tier-3: multi-LLM job-family classification (reuses the provider clients/throttle/cache).

Each judge reads title + JD + skills and returns {job_family, confidence, reasoning}. Providers are
modular (Cerebras/Mistral/Groq/Gemini/OpenRouter; add more by extending JUDGES). Out-of-vocab family
codes are coerced/retried so a stray token never loses the vote. Responses are disk-cached by
(judge, content_hash, prompt_version) → fully resumable + quota-friendly.

Two entry points:
  * `classify_one(judge_key, job)` — self-contained 3-attempt retry (used by `engine.predict` for a
    single job, when there is no central dispatcher).
  * `classify_once(judge_key, job)` — ONE attempt, cache-first; raises `RateLimited(reset_seconds)`
    on a 429 so the engine's dynamic dispatcher can cool/exhaust that provider and re-route the job
    to another. This is what the corpus run uses (per-provider rate + failover lives in the engine).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import lru_cache

from pipeline.utils.config import DATA_DIR
from pipeline.dataset import _io  # noqa: F401  (kept: provenance helpers used elsewhere in engine)
from pipeline.dataset.llm_clients import JUDGES, _MIN_INTERVAL, _client, _throttle

from .taxonomy import codes, families, prompt_catalog

log = logging.getLogger("job_family_engine.llm")
FAMILY_PROMPT_VERSION = "2"   # v2: compact prompt (TPM-safe), shorter JD window
CACHE_DIR = DATA_DIR / "labeling" / "llm_cache"


class RateLimited(Exception):
    """A provider returned 429 / rate-limit. `reset_seconds` = how long until it frees up
    (from the response header or error body; falls back to the judge's min interval)."""

    def __init__(self, reset_seconds: float):
        super().__init__(f"rate limited; reset in ~{reset_seconds:.1f}s")
        self.reset_seconds = float(reset_seconds)


def _parse_dur(s) -> float:
    """Parse a duration to seconds: '7.66s', '120ms', '2m30s', '1h23m45.6s', '1m', bare # (=seconds).
    Handles HOURS (Groq's daily-cap 429 says 'try again in 1h23m...') so it isn't read as ~1s."""
    s = str(s).strip().lower()
    try:
        if s.endswith("ms"):
            return float(s[:-2]) / 1000.0
        units = {"h": 3600.0, "m": 60.0, "s": 1.0}
        total, found = 0.0, False
        for val, unit in re.findall(r"([\d.]+)\s*([hms])", s):
            total += float(val) * units[unit]
            found = True
        return total if found else float(s)   # bare number = seconds
    except Exception:  # noqa: BLE001
        return 5.0


def _is_rate_limit(exc) -> bool:
    code = (getattr(exc, "status_code", None)
            or getattr(getattr(exc, "response", None), "status_code", None))
    if code == 429:
        return True
    msg = str(exc).lower()
    # specific phrases first; then a WORD-BOUNDARY 429 (so 'req_429abc' / '4290 tokens' don't match).
    if any(p in msg for p in ("rate limit", "ratelimit", "rate_limit", "too many requests",
                              "insufficient_quota", "exceeded your current quota")):
        return True
    return re.search(r"\b429\b", msg) is not None


# Body phrases that mean a DAILY / plan / quota cap (not a per-minute throttle) → exhaust for the run.
_HARD_LIMIT_TOKENS = ("exceeded your current quota", "quota exceeded", "per day", "requests per day",
                      "daily limit", "out of credits", "insufficient_quota")


def _reset_seconds(exc, judge_key: str) -> float:
    """Best-effort 'seconds until this provider frees up' from headers, then error body, then floor.
    A daily/plan/quota message returns a full day so the engine marks the provider exhausted and
    re-routes immediately instead of hammering it every few seconds."""
    msg = str(exc).lower()
    if any(tok in msg for tok in _HARD_LIMIT_TOKENS):
        return 86400.0
    hdr = getattr(getattr(exc, "response", None), "headers", None) or {}
    if hdr.get("retry-after-ms"):
        return _parse_dur(str(hdr["retry-after-ms"]) + "ms")
    for k in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-requests-minute",
              "x-ratelimit-reset-tokens"):
        if hdr.get(k):
            return _parse_dur(hdr[k])
    # Groq/others embed it in the message: "try again in 7.66s" / "in 2m30.5s" / "in 1h23m45.6s"
    m = re.search(r"try again in ((?:[\d.]+\s*[hms])+)", msg)
    if m:
        return _parse_dur(m.group(1))
    return _MIN_INTERVAL.get(judge_key, 2.0)


@lru_cache(maxsize=1)
def _name_to_code() -> dict:
    return {m["name"].lower(): c for c, m in families().items()}


@lru_cache(maxsize=1)
def _judge_name_to_key() -> dict:
    return {j.name: k for k, j in JUDGES.items()}


def provider_key_for(judge_name: str) -> str:
    """Map a cached record's judge NAME (e.g. 'groq-llama-3.1-8b') back to its provider KEY
    ('groq8b') so labeling_method is the same value space on live and cache-hit paths."""
    return _judge_name_to_key().get(judge_name, judge_name)


@lru_cache(maxsize=1)
def system_prompt() -> str:
    return (
        "You classify a Vietnamese/English job posting into EXACTLY ONE job-family CODE.\n\n"
        "FAMILY CODES (pick one, or OTHER if not a data/AI role):\n"
        f"{prompt_catalog()}\n\n"
        "Decide by the PRIMARY RESPONSIBILITIES (title + JD + skills), not the title alone.\n"
        'Return ONLY a JSON object: {"job_family": "<CODE>", "confidence": <0.0-1.0>, '
        '"reasoning": "<one short sentence>"}. Use a CODE exactly as written above.'
    )


def _coerce_code(v) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip().upper().replace(" ", "_")
    if s in codes():
        return s
    return _name_to_code().get(v.strip().lower())


def _build_user(job: dict) -> str:
    sk = job.get("skills")
    sk = list(sk) if sk is not None else []
    jd = job.get("jd") or job.get("role_view") or ""
    return (f"TITLE: {job.get('title') or ''}\nSKILLS: {', '.join(map(str, sk))}\n"
            f"JD: {str(jd)[:2500]}")


def _cache_path(judge_name: str, content_hash: str):
    return CACHE_DIR / judge_name / f"{content_hash}_{FAMILY_PROMPT_VERSION}.json"


def _call(judge, job: dict, sysp: str, user: str) -> dict:
    """One live API call → parsed+cached rec. Raises on network/JSON/invalid-code (caller decides)."""
    resp = _client(judge).chat.completions.create(
        model=judge.model, temperature=0, max_tokens=400,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sysp},
                  {"role": "user", "content": user}],
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    code = _coerce_code(data.get("job_family"))
    if not code:
        raise ValueError(f"bad code {data.get('job_family')!r}")
    try:
        conf = float(data.get("confidence", 0.7))
    except Exception:  # noqa: BLE001
        conf = 0.7
    rec = {"job_id": job["job_id"], "judge": judge.name, "job_family": code,
           "confidence": round(conf, 3), "reasoning": str(data.get("reasoning", ""))[:300]}
    cpath = _cache_path(judge.name, job["content_hash"])
    cpath.parent.mkdir(parents=True, exist_ok=True)
    tmp = cpath.with_suffix(".json.tmp")            # atomic write: a kill mid-write can't truncate
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cpath)
    return rec


def _read_cache(cpath) -> dict | None:
    """Read a cache file, self-healing a corrupt/truncated one (delete → returns None → re-label)."""
    try:
        return json.loads(cpath.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        try:
            cpath.unlink()
        except OSError:
            pass
        return None


def cached_any(job: dict) -> dict | None:
    """Return a cached label for this job from ANY judge (provider-agnostic resume).

    A job's family doesn't depend on which provider produced it, so on resume we reuse the first
    cached answer instead of re-spending a (different) provider's quota."""
    ch = job["content_hash"]
    for judge in JUDGES.values():
        p = _cache_path(judge.name, ch)
        if p.exists():
            rec = _read_cache(p)
            if rec is not None:
                return rec
    return None


def classify_once(judge_key: str, job: dict) -> dict:
    """ONE attempt with one judge. Cache-first. Returns rec, or raises RateLimited(reset_seconds)
    on a 429 (so the engine can re-route), or re-raises other errors for the caller to handle."""
    judge = JUDGES[judge_key]
    cpath = _cache_path(judge.name, job["content_hash"])
    if cpath.exists():
        rec = _read_cache(cpath)
        if rec is not None:
            return rec
    try:
        return _call(judge, job, system_prompt(), _build_user(job))
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limit(exc):
            raise RateLimited(_reset_seconds(exc, judge_key)) from exc
        raise


def classify_one(judge_key: str, job: dict) -> dict | None:
    """Self-contained 3-attempt retry (single-job path; honors 429 reset between attempts)."""
    judge = JUDGES[judge_key]
    cpath = _cache_path(judge.name, job["content_hash"])
    if cpath.exists():
        rec = _read_cache(cpath)
        if rec is not None:
            return rec
    sysp, user, last = system_prompt(), _build_user(job), None
    for attempt in range(1, 4):
        _throttle(judge_key)
        try:
            u = user if attempt == 1 else user + f"\n\n(Prev invalid: {last}. Return a valid CODE.)"
            return _call(judge, job, sysp, u)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:140]
            log.warning("%s attempt %d job %s: %s", judge.name, attempt, job["job_id"], last)
            wait = _reset_seconds(exc, judge_key) if _is_rate_limit(exc) else _MIN_INTERVAL.get(judge_key, 2.0)
            time.sleep(min(wait + 0.5, 30.0))
    return None
