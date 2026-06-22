"""LLM provider clients (OpenAI-compatible) for the Job Family Labeling Engine's Tier-3.

Every provider exposes an OpenAI-compatible endpoint, so one client shape covers them all via
`openai.OpenAI(base_url=..., api_key=...)`. Keys come from `.env` (never hardcoded). The engine
(`job_family_engine/`) imports `JUDGES`, `_client`, `_throttle`, `_MIN_INTERVAL` and drives the
calls / caching / failover itself — this module only owns the client objects and per-provider
request spacing.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from ..utils.config import get_secrets

log = logging.getLogger("pipeline.dataset.llm")


@dataclass(frozen=True)
class Judge:
    name: str
    base_url: str
    model: str
    key_env: str  # attribute name on Secrets


# Model IDs verified live against each provider's /models. The Cerebras account serves gpt-oss-120b
# (no Llama). Six providers give the engine plenty of aggregate capacity + failover headroom.
JUDGES: dict[str, Judge] = {
    "cerebras": Judge("cerebras-gpt-oss-120b", "https://api.cerebras.ai/v1",
                      "gpt-oss-120b", "cerebras_api_key"),
    "mistral": Judge("mistral-large", "https://api.mistral.ai/v1",
                     "mistral-large-latest", "mistral_api_key"),
    "groq": Judge("groq-llama-3.3-70b", "https://api.groq.com/openai/v1",
                  "llama-3.3-70b-versatile", "groq_api_key"),       # ~24/min, 1000/day
    "groq8b": Judge("groq-llama-3.1-8b", "https://api.groq.com/openai/v1",
                    "llama-3.1-8b-instant", "groq_api_key"),         # ~15/min, 14.4k/day (workhorse)
    "qwen": Judge("openrouter-qwen-2.5-72b", "https://openrouter.ai/api/v1",
                  "qwen/qwen-2.5-72b-instruct", "openrouter_api_key"),  # ~50/day → bonus only
    "gemini": Judge("gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "gemini-2.0-flash", "gemini_api_key"),  # free 15 rpm / 1500 rpd
}

_clients: dict[str, object] = {}

# Per-judge request-START spacing (seconds), shared across worker threads — matched to measured
# free-tier req/min. The engine's dispatcher also reserves slots, so this is a backstop.
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
