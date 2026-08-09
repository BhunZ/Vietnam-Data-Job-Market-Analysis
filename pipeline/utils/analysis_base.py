"""THE definition of the analysis base — one string, imported everywhere.

Six places had independently written this filter (`job_family_engine/integrate.py`,
`pipeline/transform/gold.py`, `analysis/validate_gold.py` and the three `analysis/*.py` P5 scripts).
They happened to agree, but nothing enforced it: any future edit to one of them would silently split the
population, and this project already shipped that exact bug once — `pipeline/transform/gold.py` filtered
on the deprecated `role_category` (597 postings) while `integrate.py` filtered on `job_family` (752), so
`skill_cooccurrence` and `gold_market_share` described different corpora and a relabel moved only one.

Rules encoded here:
  * `job_family IS NOT NULL`      — the posting was labeled at all.
  * `job_family != 'OTHER'`       — OTHER is not a data role; it is counted separately, never analysed.
  * `is_active`                   — the posting was still live at the last snapshot.
  * `is_duplicate_of IS NULL`     — cross-source duplicates collapse to one row.
  * `jf_review NOT IN (...)`      — postings the labeling engine could not settle. `manual_review` = no
                                    judge pair agreed; `domain_only` = judges agreed on the domain but
                                    not the family (those still count in `gold_domain_share`, which is
                                    why it uses ANALYSIS_BASE_DOMAIN_WHERE below).
"""

from __future__ import annotations

import sys


def force_utf8_stdout() -> None:
    """Print Vietnamese to a Windows console without crashing.

    A default Windows console is cp1252, which cannot encode `→` or any Vietnamese
    diacritic. `market_insights.py` died on exactly that — one arrow in a progress line,
    after all the work was done — and every one of these scripts prints company names and
    cities straight from the corpus, so it was luck rather than design that the others
    survived. `pipeline/__main__.py` does the same thing for the CLI; the standalone
    scripts under analysis/ never went through it.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — a console that refuses is not worth failing over
        pass


_RESOLVED = "COALESCE(jf_review, 'resolved') NOT IN ('manual_review', 'domain_only')"
_CORE = ("job_family IS NOT NULL AND job_family != 'OTHER' AND is_active "
         "AND is_duplicate_of IS NULL")

#: Family-level analysis base (market share, skills, clustering, topics, association rules).
ANALYSIS_BASE_WHERE = f"{_CORE} AND {_RESOLVED}"

#: Domain-level base: also includes `domain_only` postings, whose domain HAS consensus even though their
#: family does not. Used only by `gold_domain_share`.
ANALYSIS_BASE_DOMAIN_WHERE = (
    f"{_CORE} AND COALESCE(jf_review, 'resolved') <> 'manual_review'"
)


def qualified(where: str = ANALYSIS_BASE_WHERE, alias: str = "s") -> str:
    """Same filter with a table alias, for queries that join (e.g. `jobs_silver s JOIN jobs j`)."""
    out = where
    for col in ("job_family", "is_active", "is_duplicate_of", "jf_review"):
        out = out.replace(col, f"{alias}.{col}")
    return out
