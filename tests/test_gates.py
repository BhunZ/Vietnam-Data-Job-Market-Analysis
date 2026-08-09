"""Quality gates (pipeline/gates.py).

The gate exists to stop a broken parser from being labeled. It also has to not cry wolf
at a long gap between runs, which is what the flat 25% threshold in the roadmap would
have done to the real 2026-08-09 run.
"""

from datetime import date

import duckdb
import pytest

import pipeline.gates as G


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    db = tmp_path / "wh.duckdb"
    monkeypatch.setattr(G, "DB_PATH", db)
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE jobs (source VARCHAR, source_job_id VARCHAR, "
                "first_seen_date DATE, last_seen_date DATE, is_active BOOLEAN)")
    con.execute("CREATE TABLE job_observations (source VARCHAR, source_job_id VARCHAR, "
                "snapshot_date DATE)")
    con.close()
    return db


def _seed(db, old: int, new: int, prev_snapshot: str, run: str, source="itviec"):
    con = duckdb.connect(str(db))
    for i in range(old):
        con.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, TRUE)",
                    [source, f"old{i}", prev_snapshot, run])
    for i in range(new):
        con.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, TRUE)",
                    [source, f"new{i}", run, run])
    con.execute("INSERT INTO job_observations VALUES (?, 'x', ?)", [source, prev_snapshot])
    con.close()


# --- the allowance curve ----------------------------------------------------------

def test_a_weekly_gap_allows_the_base_share():
    assert G.allowed_new_pct(7) == pytest.approx(0.25)


def test_a_longer_gap_allows_proportionally_more():
    assert G.allowed_new_pct(14) == pytest.approx(0.50)
    assert G.allowed_new_pct(28) == pytest.approx(1.00 if G.MAX_NEW_PCT >= 1 else G.MAX_NEW_PCT)


def test_the_allowance_is_capped_however_long_the_gap():
    """Everything being new means nothing matched — the signature of an id scheme change."""
    assert G.allowed_new_pct(3650) == pytest.approx(G.MAX_NEW_PCT)


# --- the gate ---------------------------------------------------------------------

def test_a_normal_weekly_run_passes(warehouse):
    _seed(warehouse, old=1000, new=100, prev_snapshot="2026-08-02", run="2026-08-09")

    result = G.check_ingest_delta(date(2026, 8, 9))

    assert result["passed"] is True
    assert result["gap_days"] == 7
    assert result["new_pct"] == pytest.approx(0.10)


def test_a_parser_break_on_a_weekly_run_is_stopped(warehouse):
    """800 plausible new ids against a 1000 corpus after one week is not real churn."""
    _seed(warehouse, old=1000, new=800, prev_snapshot="2026-08-02", run="2026-08-09")

    with pytest.raises(G.QualityGateFailed, match="ingest delta gate FAILED"):
        G.check_ingest_delta(date(2026, 8, 9))


def test_the_same_delta_passes_when_the_gap_is_long(warehouse):
    """The real 2026-08-09 run: 8 weeks of churn, not a broken parser."""
    _seed(warehouse, old=1701, new=1490, prev_snapshot="2026-06-16", run="2026-08-09")

    result = G.check_ingest_delta(date(2026, 8, 9))

    assert result["gap_days"] == 54
    assert result["passed"] is True
    assert result["new_pct"] == pytest.approx(0.876, abs=0.001)


def test_allow_large_delta_overrides_a_failure(warehouse):
    _seed(warehouse, old=1000, new=800, prev_snapshot="2026-08-02", run="2026-08-09")

    result = G.check_ingest_delta(date(2026, 8, 9), allow_large=True)

    assert result["passed"] is False
    assert result["overridden"] is True


def test_the_first_ever_run_has_nothing_to_compare_against(warehouse):
    _seed(warehouse, old=0, new=500, prev_snapshot="2026-08-02", run="2026-08-09")
    con = duckdb.connect(str(warehouse))
    con.execute("DELETE FROM job_observations")
    con.close()

    result = G.check_ingest_delta(date(2026, 8, 9))

    assert result["passed"] is True
    assert result["corpus_before"] == 0


# --- stale sources ----------------------------------------------------------------

def test_a_source_nobody_scrapes_any_more_is_reported_stale(warehouse):
    """TopCV: blocked by DataDome since June, its postings still flagged active."""
    _seed(warehouse, old=99, new=0, prev_snapshot="2026-06-16", run="2026-06-16", source="topcv")

    stale = G.stale_sources(date(2026, 8, 9))

    assert [s["source"] for s in stale] == ["topcv"]
    assert stale[0]["active_rows"] == 99
    assert stale[0]["age_days"] == 54


def test_a_source_scraped_this_run_is_not_stale(warehouse):
    _seed(warehouse, old=100, new=10, prev_snapshot="2026-08-02", run="2026-08-09")

    assert G.stale_sources(date(2026, 8, 9)) == []
