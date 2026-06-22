"""Load the hierarchical job-family taxonomy (versioned YAML)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

TAXONOMY_VERSION = "1"
_PATH = Path(__file__).parent / "taxonomy" / f"taxonomy_v{TAXONOMY_VERSION}.yml"


@lru_cache(maxsize=1)
def _raw() -> dict:
    return yaml.safe_load(_PATH.open(encoding="utf-8"))


@lru_cache(maxsize=1)
def families() -> dict:
    """code -> {name, domain, subdomain, aliases, typical_skills, sparse}."""
    out = {}
    for dom in _raw()["domains"]:
        for sd in dom["subdomains"]:
            for f in sd["families"]:
                out[f["code"]] = {
                    "name": f["name"], "domain": dom["name"], "subdomain": sd["name"],
                    "aliases": [a.lower() for a in (f.get("aliases") or [])],
                    "typical_skills": f.get("typical_skills") or [],
                    "sparse": bool(f.get("sparse")),
                }
    return out


def codes() -> set:
    return set(families())


def meta(code: str) -> dict:
    return families().get(code, {})


def prompt_catalog() -> str:
    """Compact family catalog (code: short name, grouped) for the LLM prompt — small token
    footprint (no skill lists) to stay under provider TPM limits."""
    lines, fam = [], families()
    by_dom: dict[str, list] = {}
    for code, m in fam.items():
        if code == "OTHER":
            continue
        by_dom.setdefault(m["domain"], []).append(f"{code}={m['name']}")
    for dom, items in by_dom.items():
        lines.append(f"{dom}: " + "; ".join(items))
    lines.append("OTHER = not a data/AI role")
    return "\n".join(lines)
