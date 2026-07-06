"""Validation checks for Milestone 6.

Reads the shipped DuckDB warehouse in read-only mode and prints evidence that
Family Gold tables are internally consistent enough for analysis.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"


def dup_grain(con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> int:
    rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    counts = Counter(rows)
    return sum(1 for n in counts.values() if n > 1)


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)

    analysis_base = con.execute(
        """
        SELECT COUNT(*)
        FROM jobs_silver
        WHERE job_family IS NOT NULL
          AND job_family != 'OTHER'
          AND is_active
          AND is_duplicate_of IS NULL
        """
    ).fetchone()[0]
    gold_jobs = con.execute("SELECT COUNT(*) FROM gold_jobs").fetchone()[0]
    market_total = con.execute(
        "SELECT SUM(n), ROUND(SUM(pct), 1) FROM gold_market_share"
    ).fetchone()

    print("analysis_base", analysis_base)
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

