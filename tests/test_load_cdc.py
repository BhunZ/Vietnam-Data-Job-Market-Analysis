"""CDC upsert semantics (pipeline/transform/load.py): new/removed/idempotent.

Uses a temp warehouse + temp bronze via monkeypatching the module globals, so it touches
no real data and needs no network.
"""

import json
from datetime import date

import duckdb

import pipeline.transform.load as L
import pipeline.utils.bronze as B


def _put(base, source, ids, run_date="2026-01-01"):
    """Write one dated Bronze snapshot, the way `scrape` does."""
    B.write_snapshot(
        source, run_date,
        (json.dumps({"source": source, "source_job_id": i, "title_raw": f"job {i}",
                     "skills_raw": [], "posted_date_raw": None}) for i in ids),
    )


def _val(db, sql):
    con = duckdb.connect(str(db), read_only=True)
    v = con.execute(sql).fetchone()[0]
    con.close()
    return v


def test_cdc_new_removed_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DB_PATH", tmp_path / "wh.duckdb")
    monkeypatch.setattr(B, "BRONZE_DIR", tmp_path / "bronze")
    monkeypatch.setattr(L, "BRONZE", tmp_path / "bronze")
    db = tmp_path / "wh.duckdb"

    # VietnamWorks is the only full-scan source (its sweep finishes inside the page cap);
    # TopDev is coverage-limited, so it needs two consecutive misses before a removal.
    # day 1: vietnamworks {a,b} (full scan), topdev {x,y} (miss-streak)
    _put(tmp_path, "vietnamworks", ["a", "b"], "2026-01-01")
    _put(tmp_path, "topdev", ["x", "y"], "2026-01-01")
    L.upsert_run(date(2026, 1, 1))
    assert _val(db, "SELECT count(*) FROM jobs") == 4
    assert _val(db, "SELECT count(*) FILTER(WHERE is_active) FROM jobs") == 4

    # day 2: vietnamworks drops b + adds c; topdev drops y
    _put(tmp_path, "vietnamworks", ["a", "c"], "2026-01-02")
    _put(tmp_path, "topdev", ["x"], "2026-01-02")
    L.upsert_run(date(2026, 1, 2))
    # full_scan source: b removed immediately
    assert _val(db, "SELECT is_active FROM jobs WHERE source='vietnamworks' AND source_job_id='b'") is False
    # new id c
    assert _val(db, "SELECT first_seen_date FROM jobs WHERE source='vietnamworks' AND source_job_id='c'") == date(2026, 1, 2)
    # miss-streak source: y still active after 1 miss
    assert _val(db, "SELECT is_active FROM jobs WHERE source='topdev' AND source_job_id='y'") is True
    assert _val(db, "SELECT miss_streak FROM jobs WHERE source='topdev' AND source_job_id='y'") == 1

    # idempotent re-run of day 2: no dup rows, miss_streak not double-counted
    L.upsert_run(date(2026, 1, 2))
    assert _val(db, "SELECT count(*) FROM jobs") == 5
    assert _val(db, "SELECT miss_streak FROM jobs WHERE source='topdev' AND source_job_id='y'") == 1

    # day 3: y still missing -> 2nd miss -> removed
    _put(tmp_path, "topdev", ["x"], "2026-01-03")
    L.upsert_run(date(2026, 1, 3))
    assert _val(db, "SELECT is_active FROM jobs WHERE source='topdev' AND source_job_id='y'") is False

    # Every run left its own snapshot behind — the point of dating Bronze. The day-1
    # file must still hold day-1 content, or the warehouse is not rebuildable from raw.
    assert [p.name for p in B.list_snapshots("topdev")] == [
        "2026-01-01.jsonl.gz", "2026-01-02.jsonl.gz", "2026-01-03.jsonl.gz"]
    day1 = {r["source_job_id"] for r in B.iter_rows(B.snapshot_path("topdev", "2026-01-01"))}
    assert day1 == {"x", "y"}


def test_a_truncating_source_is_not_treated_as_a_full_scan():
    """itviec hits its page cap, so a posting past the last page is not a removal.

    It was flagged full-scan until 2026-08-09, which would have stamped `removed_date` on
    every posting that slipped past page 10 of the `ai-engineer` category — a fabricated
    removal, and one nothing would have surfaced.
    """
    truncating = {"itviec", "careerviet", "topdev", "glints", "vieclam24h"}
    assert truncating.isdisjoint({s for s, full in L.FULL_SCAN.items() if full})
    assert L.FULL_SCAN["vietnamworks"] is True


def test_retired_sources_are_gone_from_the_scan_policy():
    """TopCV was removed; leaving it here would imply the pipeline still reads it."""
    assert "topcv" not in L.FULL_SCAN
