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

from pipeline.utils.analysis_base import force_utf8_stdout, ANALYSIS_BASE_WHERE


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"


def dup_grain(con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> int:
    rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    counts = Counter(rows)
    return sum(1 for n in counts.values() if n > 1)


def main() -> int:
    """Print the evidence, then return an exit code so this can gate a pipeline run.

    It used to only print. A check nobody can fail is a report, not a check: `pipeline all`
    would have happily finished on a warehouse whose Gold tables disagreed with each other.
    """
    force_utf8_stdout()
    failures: list[str] = []
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
        n_dup = dup_grain(con, table, cols)
        print(f"{table}_duplicate_grain", n_dup)
        if n_dup:
            failures.append(f"{table}: {n_dup} rows break the declared grain {cols}")

    cooc = con.execute(
        "SELECT skill_a, skill_b FROM gold_skill_cooccurrence"
    ).fetchall()
    bad_order = sum(1 for a, b in cooc if a >= b)
    print("gold_skill_cooccurrence_bad_pair_order", bad_order)
    if bad_order:
        failures.append(f"gold_skill_cooccurrence: {bad_order} pairs not stored as skill_a < skill_b, "
                        "so the same pair can appear twice")

    # Gold must describe the analysis base and nothing else. When these drift apart it is
    # normally because one writer filters on a different column than another — a bug this
    # project has actually shipped before (see pipeline/utils/analysis_base.py).
    if market_total[0] is not None and market_total[0] != analysis_base:
        failures.append(f"gold_market_share sums to {market_total[0]} but the analysis base holds "
                        f"{analysis_base} postings — the two describe different corpora")
    if market_total[1] is not None and abs(market_total[1] - 100.0) > 0.5:
        failures.append(f"gold_market_share percentages sum to {market_total[1]}, not 100")

    print("top5_market_share")
    for row in con.execute(
        "SELECT job_family, n, pct FROM gold_market_share ORDER BY n DESC LIMIT 5"
    ).fetchall():
        print(row)

    con.close()

    if failures:
        print(f"\nVALIDATION FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nVALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

