"""Configuration & secrets loading.

Secrets come exclusively from environment variables loaded from a gitignored ``.env``
via python-dotenv. Source config comes from ``config/sources.yml``. Nothing here ever
hardcodes a credential.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Repo root = two levels up from this file (pipeline/utils/config.py -> repo/).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CONFIG_DIR = REPO_ROOT / "config"

# Load .env once, on import. Values already in the environment win.
load_dotenv(REPO_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Secrets:
    scraper_api_key: str | None
    scraper_api_key_secondary: str | None
    # LLM-judge providers (used by the dataset annotation layer; loaded from .env).
    groq_api_key: str | None = None
    cerebras_api_key: str | None = None
    mistral_api_key: str | None = None
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None

    @property
    def keys(self) -> list[str]:
        """ScraperAPI keys available for rotation (primary first), non-empty only."""
        return [k for k in (self.scraper_api_key, self.scraper_api_key_secondary) if k]


def get_secrets() -> Secrets:
    return Secrets(
        scraper_api_key=os.getenv("SCRAPER_API_KEY") or None,
        scraper_api_key_secondary=os.getenv("SCRAPER_API_KEY_SECONDARY") or None,
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY") or None,
        mistral_api_key=os.getenv("MISTRAL_API_KEY") or None,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
    )


@lru_cache(maxsize=1)
def load_sources_config() -> dict:
    path = CONFIG_DIR / "sources.yml"
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def source_config(source: str) -> dict:
    """Merged config for one source: defaults overlaid with the source block."""
    cfg = load_sources_config()
    merged = dict(cfg.get("defaults", {}))
    merged.update(cfg.get("sources", {}).get(source, {}))
    return merged
