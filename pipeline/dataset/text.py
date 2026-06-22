"""Build the LOCAL-ONLY text artifact `data/dataset/text/jobs_text.parquet`.

One row per silver job, carrying the full title + JD text plus the fields needed for
discovery and (later) leakage-safe splitting:
  - `dup_group_id`  : survivor job_id (own id if survivor) — cross-source duplicates share
                      a group so train/val/test never leak the same job across splits.
  - `lang` / `vi_ratio` : crude VN/EN tag from diacritic ratio (no extra dependency).
  - `content_hash`  : stable hash of (title + jd + skills) for provenance keying.
  - `role_view`     : the boilerplate-trimmed "role-relevant view" embedded in Phase 1.

This file holds raw scraped text → it is gitignored and NOT part of any public release;
derived embeddings/labels (keyed by job_id + content_hash) are what would be published.

Run:  python -m pipeline discover   (this is the first step)
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata

import duckdb
import pandas as pd

from ..utils.config import DATA_DIR
from . import _io

log = logging.getLogger("pipeline.dataset.text")
DB_PATH = DATA_DIR / "warehouse.duckdb"
SCHEMA_VERSION = "jobs_text/1"

# Vietnamese-specific base letters (NFD strips tone marks; these survive as base chars).
_VI_CHARS = set("ăâđêôơư")
_WS = re.compile(r"\s+")
# Recruiter boilerplate lines to drop from the role-relevant view (light, not exhaustive).
_BOILERPLATE = re.compile(
    r"(quyền lợi|phúc lợi|benefits?|chế độ|why you'?ll love|about us|về chúng tôi|"
    r"company overview|equal opportunity|how to apply|cách thức ứng tuyển|nộp hồ sơ)",
    re.I)


def _vi_ratio(text: str) -> float:
    """Fraction of alphabetic chars that are Vietnamese-specific (precomposed base or
    carry a combining tone mark) — a cheap VN/EN signal without a language-detect dep."""
    if not text:
        return 0.0
    alpha = vi = 0
    for ch in text.lower():
        if ch.isalpha():
            alpha += 1
            base = unicodedata.normalize("NFD", ch)
            if ch in _VI_CHARS or any(unicodedata.category(c) == "Mn" for c in base):
                vi += 1
    return round(vi / alpha, 4) if alpha else 0.0


def _role_view(title: str | None, jd: str | None, skills: list[str]) -> str:
    """Title + skills + boilerplate-trimmed JD — the text we embed for role structure."""
    jd = jd or ""
    kept = [ln for ln in jd.splitlines() if ln.strip() and not _BOILERPLATE.search(ln)]
    jd_clean = _WS.sub(" ", " ".join(kept)).strip()
    parts = [
        (title or "").strip(),
        ("Skills: " + ", ".join(skills)) if skills else "",
        jd_clean[:4000],  # cap very long JDs so one posting can't dominate the embedding
    ]
    return _WS.sub(" ", " \n".join(p for p in parts if p)).strip()


def build_jobs_text() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("""
        SELECT s.job_id, s.source, s.source_job_id, s.title_clean, s.role_category,
               s.seniority, s.city, s.region, s.company, s.company_type, s.company_key,
               s.skills, s.n_skills, s.is_active, s.is_duplicate_of,
               j.title_raw, j.description_raw
        FROM jobs_silver s JOIN jobs j USING (source, source_job_id)
    """).df()
    con.close()
    df = df.astype(object).where(pd.notnull(df), None)

    rows = []
    for r in df.to_dict("records"):
        skills = json.loads(r["skills"]) if r["skills"] else []
        title = r["title_clean"] or r["title_raw"]
        jd = r["description_raw"]
        view = _role_view(title, jd, skills)
        rows.append({
            "job_id": r["job_id"],
            "source": r["source"],
            "title": title,
            "jd": jd,
            "skills": skills,
            "n_skills": r["n_skills"],
            "role_category": r["role_category"],         # current rule label (for crosstab)
            "seniority": r["seniority"],
            "city": r["city"], "region": r["region"],
            "company": r["company"], "company_type": r["company_type"],
            "is_active": bool(r["is_active"]) if r["is_active"] is not None else None,
            # group-aware split key: survivor id if this row is a duplicate, else own id
            "dup_group_id": r["is_duplicate_of"] or r["job_id"],
            "role_view": view,
            "view_len": len(view),
            "lang": "vi" if _vi_ratio(view) >= 0.06 else "en",
            "vi_ratio": _vi_ratio(view),
            "content_hash": _io.content_hash(title or "", jd or "", " ".join(skills)),
        })
    return pd.DataFrame(rows)


def run_build_text() -> pd.DataFrame:
    df = build_jobs_text()
    out = _io.TEXT_DIR / "jobs_text.parquet"
    _io.write_parquet(df, out, schema_version=SCHEMA_VERSION, produced_by="dataset.text")
    log.info("jobs_text: %d rows -> %s", len(df), out)
    return df
