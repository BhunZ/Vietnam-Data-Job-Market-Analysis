"""Tier-1: high-precision rule/keyword classification on the job TITLE.

Matches family aliases (from the versioned taxonomy YAML) against the normalized title with
word boundaries. Title-only on purpose (so a required *skill* never mislabels the role — the old
skill↔role collision bug). Separators (-, _, /) are normalized to spaces (old hyphen/underscore bug).
Returns a high-confidence family only for specific phrases; ambiguous titles defer to Tier-2/3.
"""

from __future__ import annotations

import re

from .taxonomy import families

_WS = re.compile(r"\s+")
_SEP = re.compile(r"[_\-/]+")
# specific single-token aliases that are safe as high-confidence on their own
_STRONG_SINGLE = {"dba", "mlops", "dataops", "etl", "nlp", "rag", "langchain"}


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    return _WS.sub(" ", _SEP.sub(" ", s).strip().lower())


def _contains(hay: str, pat: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(pat) + r"(?!\w)", hay) is not None


def tier1(title) -> tuple[str | None, float, str | None]:
    """Return (family_code | None, confidence, matched_alias)."""
    t = _norm(title)
    if not t:
        return None, 0.0, None
    best_code, best_alias = None, ""
    for code, m in families().items():
        if code == "OTHER":
            continue
        for a in m["aliases"]:
            an = _norm(a)
            if not an or not _contains(t, an):
                continue
            specific = (" " in an) or (an in _STRONG_SINGLE)
            if specific and len(an) > len(best_alias):
                best_code, best_alias = code, an
    if best_code:
        return best_code, 0.9, best_alias
    return None, 0.0, None
