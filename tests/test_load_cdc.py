"""CDC upsert semantics (pipeline/transform/load.py): new/removed/idempotent.

Uses a temp warehouse + temp bronze via monkeypatching the module globals, so it touches
no real data and needs no network.
"""

import json
from datetime import date

import duckdb

import pipeline.transform.load as L


def _put(base, source, ids):
    d = base / "bronze" / source
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.jsonl").write_text(
        "\n".join(json.dumps({"source": source, "source_job_id": i, "title_raw": f"job {i}",
                              "skills_raw": [], "posted_date_raw": None}) for i in ids),
        encoding="utf-8")


def _val(db, sql):
    con = duckdb.connect(str(db), read_only=True)
    v = con.execute(sql).fetchone()[0]
    con.close()
    return v


def test_cdc_new_removed_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DB_PATH", tmp_path / "wh.duckdb")
    monkeypatch.setattr(L, "BRONZE", tmp_path / "bronze")
    db = tmp_path / "wh.duckdb"

    # day 1: itviec {a,b} (full_scan), topdev {x,y} (miss-streak)
    _put(tmp_path, "itviec", ["a", "b"])
    _put(tmp_path, "topdev", ["x", "y"])
    L.upsert_run(date(2026, 1, 1))
    assert _val(db, "SELECT count(*) FROM jobs") == 4
    assert _val(db, "SELECT count(*) FILTER(WHERE is_active) FROM jobs") == 4

    # day 2: itviec drops b + adds c; topdev drops y
    _put(tmp_path, "itviec", ["a", "c"])
    _put(tmp_path, "topdev", ["x"])
    L.upsert_run(date(2026, 1, 2))
    # full_scan source: b removed immediately
    assert _val(db, "SELECT is_active FROM jobs WHERE source='itviec' AND source_job_id='b'") is False
    # new id c
    assert _val(db, "SELECT first_seen_date FROM jobs WHERE source='itviec' AND source_job_id='c'") == date(2026, 1, 2)
    # miss-streak source: y still active after 1 miss
    assert _val(db, "SELECT is_active FROM jobs WHERE source='topdev' AND source_job_id='y'") is True
    assert _val(db, "SELECT miss_streak FROM jobs WHERE source='topdev' AND source_job_id='y'") == 1

    # idempotent re-run of day 2: no dup rows, miss_streak not double-counted
    L.upsert_run(date(2026, 1, 2))
    assert _val(db, "SELECT count(*) FROM jobs") == 5
    assert _val(db, "SELECT miss_streak FROM jobs WHERE source='topdev' AND source_job_id='y'") == 1

    # day 3: y still missing -> 2nd miss -> removed
    _put(tmp_path, "topdev", ["x"])
    L.upsert_run(date(2026, 1, 3))
    assert _val(db, "SELECT is_active FROM jobs WHERE source='topdev' AND source_job_id='y'") is False
