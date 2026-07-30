"""Smoke test for the contract the analysis layer depends on.

Replaces `test_collect_table.py` and `test_connect_duckdb.py`, which pytest collected but which asserted
NOTHING (0 asserts, 0 test functions): they ran `SELECT *` at import time and printed. They inflated the
test count while verifying nothing. The genuine concern behind them — "can someone open the shipped
warehouse and read the tables the analysis needs?" — is worth a test, so it is one here.
"""

from __future__ import annotations

import duckdb
import pytest

from pipeline.utils.analysis_base import ANALYSIS_BASE_WHERE
from pipeline.utils.config import DATA_DIR

DB = DATA_DIR / "warehouse.duckdb"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="shipped warehouse not present")

FAMILY_GOLD = ["gold_jobs", "gold_domain_share", "gold_market_share", "gold_family_skill",
               "gold_company", "gold_location", "gold_seniority", "gold_skill_cooccurrence"]


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def test_family_gold_tables_exist(con):
    have = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert set(FAMILY_GOLD) <= have, f"missing: {set(FAMILY_GOLD) - have}"


def test_jobs_silver_carries_the_label_columns(con):
    cols = {r[0] for r in con.execute("DESCRIBE jobs_silver").fetchall()}
    assert {"job_family", "jf_domain", "jf_subdomain", "jf_method", "jf_review"} <= cols


def test_market_share_matches_the_analysis_base(con):
    """The one invariant that catches a population split — the bug where `pipeline gold` filtered on the
    deprecated `role_category` (597 rows) while `integrate` used `job_family` (752)."""
    base = con.execute(f"SELECT COUNT(*) FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE}").fetchone()[0]
    gold = con.execute("SELECT SUM(n) FROM gold_market_share").fetchone()[0]
    assert base == gold, f"analysis base {base} != gold_market_share total {gold}"


def test_market_share_percentages_sum_to_100(con):
    total = con.execute("SELECT SUM(pct) FROM gold_market_share").fetchone()[0]
    assert 99.0 <= total <= 101.0, total          # rounding to 1dp across ~20 rows


def test_domain_base_is_never_smaller_than_family_base(con):
    """`gold_domain_share` also counts `domain_only` postings, so it is >= the family base by design."""
    fam = con.execute("SELECT SUM(n) FROM gold_market_share").fetchone()[0]
    dom = con.execute("SELECT SUM(n) FROM gold_domain_share").fetchone()[0]
    assert dom >= fam


def test_unresolved_labels_never_reach_the_family_tables(con):
    leaked = con.execute(
        "SELECT COUNT(*) FROM jobs_silver WHERE jf_review IN ('manual_review','domain_only') "
        "AND job_family <> 'OTHER' AND is_active AND is_duplicate_of IS NULL "
        f"AND job_id IN (SELECT job_id FROM jobs_silver WHERE {ANALYSIS_BASE_WHERE})"
    ).fetchone()[0]
    assert leaked == 0


def test_no_duplicate_grain_in_family_skill(con):
    dupes = con.execute("SELECT COUNT(*) FROM (SELECT job_family, skill FROM gold_family_skill "
                        "GROUP BY 1,2 HAVING COUNT(*) > 1)").fetchone()[0]
    assert dupes == 0
