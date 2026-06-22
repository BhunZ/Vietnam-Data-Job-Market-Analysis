"""LLM judge clients (OpenAI-compatible) for 3-judge annotation.

All three providers expose an OpenAI-compatible endpoint, so one client shape covers them via
`openai.OpenAI(base_url=..., api_key=...)`. Keys come from `.env` (never hardcoded). Each judge
returns a JSON object validated against `schema.JudgeAnnotation` (retry on invalid). Responses are
disk-cached by (judge, content_hash, prompt_version) → resumable + idempotent + quota-friendly.

Judge selection (quota-aware, per plan): base reliable pair = Cerebras Llama-3.3-70B + Mistral-Large
(different families, generous quota); OpenRouter Qwen-2.5-72B is the optional 3rd/tie-breaker
(OpenRouter free ≈50 req/day → call it only when the base pair disagrees).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

from ..utils.config import get_secrets
from . import _io
from .prompt import PROMPT_VERSION, prompt_hash
from .schema import JudgeAnnotation

log = logging.getLogger("pipeline.dataset.llm")
CACHE_DIR = _io.ANNOTATION_DIR / "cache"


@dataclass(frozen=True)
class Judge:
    name: str
    base_url: str
    model: str
    key_env: str  # attribute name on Secrets


# Model IDs verified live against each provider's /models (2026-06-20). This Cerebras account
# serves gpt-oss-120b / zai-glm-4.7 (no Llama) — gpt-oss-120b chosen as a distinct family from
# Mistral and Qwen, giving 3 independent lineages (OpenAI-OSS · Mistral · Qwen).
JUDGES: dict[str, Judge] = {
    "cerebras": Judge("cerebras-gpt-oss-120b", "https://api.cerebras.ai/v1",
                      "gpt-oss-120b", "cerebras_api_key"),
    "mistral": Judge("mistral-large", "https://api.mistral.ai/v1",
                     "mistral-large-latest", "mistral_api_key"),
    "groq": Judge("groq-llama-3.3-70b", "https://api.groq.com/openai/v1",
                  "llama-3.3-70b-versatile", "groq_api_key"),       # 1000/day → tiebreaker option
    "groq8b": Judge("groq-llama-3.1-8b", "https://api.groq.com/openai/v1",
                    "llama-3.1-8b-instant", "groq_api_key"),         # 14.4k/day → fast base 2nd vote
    "qwen": Judge("openrouter-qwen-2.5-72b", "https://openrouter.ai/api/v1",
                  "qwen/qwen-2.5-72b-instruct", "openrouter_api_key"),  # ~50/day → not at scale
    "gemini": Judge("gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "gemini-2.0-flash", "gemini_api_key"),  # free 15 rpm / 1500 rpd → high-daily base
}
# Base pair = two HIGH-QUOTA, FAST, separate-account models (run in parallel): Cerebras gpt-oss-120b
# (strong anchor) + Groq Llama-3.1-8b (fast 2nd vote). Mistral-large (1 RPS, slow) is the TIEBREAKER
# only — invoked on the disagreement subset, so its rate limit doesn't bottleneck the bulk run.
# Single strong judge by default (Cerebras gpt-oss-120b) — free-tier TPM/RPM can't sustain a 2-LLM
# vote over ~1k jobs in reasonable time. Multi-LLM voting is supported (add judges here) but optional.
BASE_JUDGES = ["cerebras"]
TIEBREAKER = "mistral"  # unused while single-judge; kept for modular re-enable

_clients: dict[str, object] = {}

# Per-judge request-START rate limit (seconds between starts), shared across worker threads.
# Mistral free tier ≈ 1 req/s → 1.2s keeps us safely under it; OpenRouter free is rare (tiebreaker).
# Intervals matched to MEASURED free-tier limits (req/min): cerebras 5, mistral 4, groq-8b ~15
# (6k TPM), groq-70b ~24 (12k TPM). Multi-provider distributor (engine) spreads load by capacity.
_MIN_INTERVAL = {"cerebras": 12.0, "mistral": 15.0, "groq8b": 4.0, "groq": 2.5, "qwen": 2.0,
                 "gemini": 4.0}
_gate = {k: threading.Lock() for k in JUDGES}
_last_start = {k: 0.0 for k in JUDGES}


def _throttle(judge_key: str) -> None:
    interval = _MIN_INTERVAL.get(judge_key, 0.0)
    if interval <= 0:
        return
    with _gate[judge_key]:
        wait = interval - (time.time() - _last_start[judge_key])
        if wait > 0:
            time.sleep(wait)
        _last_start[judge_key] = time.time()


def _client(judge: Judge):
    if judge.name not in _clients:
        from openai import OpenAI
        key = getattr(get_secrets(), judge.key_env)
        if not key:
            raise RuntimeError(f"missing {judge.key_env} in .env for judge {judge.name}")
        _clients[judge.name] = OpenAI(base_url=judge.base_url, api_key=key, timeout=60)
    return _clients[judge.name]


def _cache_path(judge: Judge, content_hash: str):
    return CACHE_DIR / judge.name / f"{content_hash}_{PROMPT_VERSION}.json"


def annotate_one(judge_key: str, job: dict, system_prompt: str,
                 use_cache: bool = True) -> dict | None:
    """Annotate one job with one judge. Returns a provenance-stamped dict or None on failure."""
    judge = JUDGES[judge_key]
    ch = job["content_hash"]
    cpath = _cache_path(judge, ch)
    if use_cache and cpath.exists():
        return json.loads(cpath.read_text(encoding="utf-8"))

    user = (f"TITLE: {job.get('title') or ''}\n\n"
            f"JOB DESCRIPTION:\n{(job.get('jd') or job.get('role_view') or '')[:6000]}")
    last_err = None
    for attempt in range(1, 4):
        _throttle(judge_key)   # respect per-judge request-rate limit (esp. Mistral 1 RPS)
        t0 = time.time()
        try:
            resp = _client(judge).chat.completions.create(
                model=judge.model, temperature=0, max_tokens=1500,  # avoid JSON truncation
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user
                           + ("" if attempt == 1 else f"\n\n(Previous attempt invalid: {last_err}. "
                              "Return a valid JSON object with the exact fields.)")}],
            )
            raw = resp.choices[0].message.content or ""
            ann = JudgeAnnotation(**json.loads(raw))  # validates vocab; raises on bad
            rec = {
                "job_id": job["job_id"], "content_hash": ch,
                "judge": judge.name, "model": judge.model,
                "prompt_version": PROMPT_VERSION,
                **ann.model_dump(),
                "latency_ms": int((time.time() - t0) * 1000),
                "raw_sha256": _io.content_hash(raw),
                "ok": True,
            }
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            return rec
        except Exception as exc:  # noqa: BLE001  (network / JSON / validation)
            last_err = str(exc)[:160]
            log.warning("%s attempt %d/%d job %s: %s", judge.name, attempt, 3, job["job_id"], last_err)
            time.sleep(min(2 ** attempt, 12))  # backoff (also helps 429)
    log.error("%s FAILED job %s: %s", judge.name, job["job_id"], last_err)
    return None


def smoke_test(judge_key: str) -> dict | None:
    """One tiny live call to verify connectivity + structured output for a judge."""
    from .prompt import build_prompt
    job = {"job_id": "smoke:1", "content_hash": "smoke", "title": "Senior Data Engineer",
           "jd": "Build and operate ETL pipelines, data warehouse on AWS, Airflow, SQL, Python."}
    return annotate_one(judge_key, job, build_prompt(), use_cache=False)
