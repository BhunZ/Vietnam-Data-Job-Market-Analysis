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
                    "gemini-2.0-flash", "gemini_api_key"),  # free 15 rpm / 1500 rpd (quota resets daily)
    # --- Extra free-tier judges, probe-verified (2026-07). Auto-activate if the key is present. ---
    "sambanova": Judge("sambanova-llama-3.3-70b", "https://api.sambanova.ai/v1",
                       "Meta-Llama-3.3-70B-Instruct", "sambanova_api_key"),
    # GitHub Models needs a fine-grained PAT with the Account -> "Models" permission (a repo-scoped
    # token 403s with `no_access`). Different lineage from the Llama/Qwen judges → useful for voting.
    "github": Judge("github-gpt-4o-mini", "https://models.github.ai/inference",
                    "openai/gpt-4o-mini", "github_models_token"),
    # 9Router combo added dynamically below (its base_url is a runtime localhost endpoint).
    # --- Probe-disabled (2026-07): OpenRouter ':free' slugs are paid-only now (404); direct NVIDIA
    #     NIM endpoint is unreachable here (connection timeout); GitHub PAT lacks Models permission
    #     (403). gemini_lite removed (free daily quota exhausts in 1-2 calls). These free providers
    #     are better reached via the local 9Router proxy (single OpenAI-compatible endpoint). ---
}

# Register the 9Router combo as one judge when its endpoint + key are set in .env. 9Router routes each
# call to a live/connected free model out of its combo and does its own failover, so from here it is a
# single reliable, high-capacity endpoint. (Individual 9Router model ids are flaky — some aren't
# connected / don't honor JSON mode — so we use the combo, not per-model judges.)
_sec = get_secrets()
if _sec.ninerouter_base_url and _sec.ninerouter_api_key:
    JUDGES["ninerouter"] = Judge("ninerouter-free-combo", _sec.ninerouter_base_url,
                                 "Free_tier_combo", "ninerouter_api_key")

# Cloudflare Workers AI — free daily allocation, and a model lineage independent of the Groq/Cerebras/
# Mistral pool. Registered dynamically because the OpenAI-compatible base_url embeds the account id.
if _sec.cf_account_id and _sec.cf_api_token:
    # Probed 2026-07-25: llama-3.3-70b-fp8-fast and mistralai/mistral-small-3.1-24b both work;
    # llama-3.1-8b is 410-deprecated and qwen2.5-coder breaks JSON mode. Using llama-70b, NOT
    # mistral-small, because mistral-small shares a lab with the `mistral` judge it would arbitrate
    # against — an arbiter must not be correlated with one of the sides it is breaking a tie between.
    JUDGES["cloudflare"] = Judge(
        "cloudflare-llama-3.3-70b",
        f"https://api.cloudflare.com/client/v4/accounts/{_sec.cf_account_id}/ai/v1",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "cf_api_token")

_clients: dict[str, object] = {}

# Per-judge request-START spacing (seconds), shared across worker threads — matched to measured
# free-tier req/min. The engine's dispatcher also reserves slots, so this is a backstop.
# ~30% headroom over the measured free-tier ceiling: running slightly under the limit means far
# fewer 429s, and each 429 costs a reset-sleep — so conservative spacing is a NET speed-up, not a
# slowdown (esp. once voting multiplies call volume). New providers use safe-guess intervals.
_MIN_INTERVAL = {"cerebras": 13.0, "mistral": 16.0, "groq8b": 5.0, "groq": 3.5, "qwen": 2.5,
                 "gemini": 5.0, "sambanova": 3.0, "ninerouter": 2.5, "cloudflare": 2.0,
                 "github": 4.0}
# A judge missing here is silently UNTHROTTLED (`_throttle` returns on interval<=0) and, worse, its
# 429s fall back to a 2s reset, which is below EXHAUST_RESET, so the engine never marks it exhausted
# and re-probes a dead provider on every remaining job. `github` was missing exactly this way.
assert set(JUDGES) == set(_MIN_INTERVAL), (
    f"every judge needs a rate interval; missing={set(JUDGES) - set(_MIN_INTERVAL)}, "
    f"stale={set(_MIN_INTERVAL) - set(JUDGES)}")
_TIMEOUT = {"ninerouter": 90}   # per-judge client timeout override (seconds); default 15
_gate = {k: threading.Lock() for k in JUDGES}
_last_start = {k: 0.0 for k in JUDGES}


def _judge_key(judge: Judge) -> str:
    """Reverse-lookup a judge's pool key from its Judge object (needed for per-key config)."""
    return next((k for k, j in JUDGES.items() if j.name == judge.name), judge.name)


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
        # 15s suits direct provider APIs; a local router that chains to free upstreams needs much
        # longer or every call dies on timeout (9Router took >15s per call and produced zero votes).
        timeout = _TIMEOUT.get(_judge_key(judge), 15)
        _clients[judge.name] = OpenAI(base_url=judge.base_url, api_key=key, timeout=timeout)
    return _clients[judge.name]
