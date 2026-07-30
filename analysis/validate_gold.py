"""Validation checks for Milestone 6.

Reads the shipped DuckDB warehouse in read-only mode and prints evidence that
Family Gold tables are internally consistent enough for analysis.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import duckdb

# These run as standalone scripts (`python analysis/<name>.py`), so the repo root is not on sys.path
# by default — add it before importing the shared analysis-base definition.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"


def dup_grain(con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> int:
    rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    counts = Counter(rows)
    return sum(1 for n in counts.values() if n > 1)


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)

    # Must mirror job_family_engine/integrate.py exactly, including the jf_review exclusion — jobs no
    # judge pair agreed on are NOT part of the analysis base. Without that clause this check reported
    # 729 against a Gold total of 667 and looked like a data bug.
    analysis_base = con.execute(
        f"SELECT COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}"
    ).fetchone()[0]
    unresolved = con.execute(
        "SELECT COUNT(*) FROM jobs_silver WHERE jf_review = 'manual_review' AND is_active "
        "AND is_duplicate_of IS NULL AND job_family != 'OTHER'"
    ).fetchone()[0]
    gold_jobs = con.execute("SELECT COUNT(*) FROM gold_jobs").fetchone()[0]
    market_total = con.execute(
        "SELECT SUM(n), ROUND(SUM(pct), 1) FROM gold_market_share"
    ).fetchone()

    print("analysis_base", analysis_base)
    print("excluded_unresolved(non-OTHER)", unresolved)
    print("gold_jobs", gold_jobs)
    print("gold_market_total_n", market_total[0])
    print("gold_market_total_pct", market_total[1])

    checks = {
        "gold_family_skill": ["job_family", "skill"],
        "gold_company": ["company_type", "job_family"],
        "gold_location": ["region", "city", "job_family"],
        "gold_seniority": ["seniority", "job_family"],
        "gold_skill_cooccurrence": ["skill_a", "skill_b"],
    }
    for table, cols in checks.items():
        print(f"{table}_duplicate_grain", dup_grain(con, table, cols))

    cooc = con.execute(
        "SELECT skill_a, skill_b FROM gold_skill_cooccurrence"
    ).fetchall()
    print("gold_skill_cooccurrence_bad_pair_order", sum(1 for a, b in cooc if a >= b))

    print("top5_market_share")
    for row in con.execute(
        "SELECT job_family, n, pct FROM gold_market_share ORDER BY n DESC LIMIT 5"
    ).fetchall():
        print(row)

    con.close()


if __name__ == "__main__":
    main()

