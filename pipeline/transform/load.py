"""Incremental load: Bronze (`data/bronze/<source>/latest.jsonl`) → DuckDB warehouse.

Master `jobs` table (one row per source+id) tracks state across runs via UPSERT (CDC):
new ids inserted (first_seen=run_date), seen ids refreshed (last_seen=run_date), and ids
that disappear get marked removed. `job_observations` logs (id, snapshot_date) per run for
trend. Idempotent: re-running the same run_date never duplicates rows or double-counts.

Run:  python -m pipeline load [--run-date YYYY-MM-DD]
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

import duckdb
import pandas as pd

from ..utils.config import DATA_DIR
from .dates import parse_posted_date

log = logging.getLogger("pipeline.load")

DB_PATH = DATA_DIR / "warehouse.duckdb"
BRONZE = DATA_DIR / "bronze"
MISS_STREAK_REMOVE = 2  # for coverage-limited sources, mark removed after K consecutive misses

# Sources we scan completely each run → a missing id means truly removed (mark immediately).
# Coverage-limited sources (paginate caps / browser / filtered) use the miss-streak instead.
FULL_SCAN = {"itviec": True, "vietnamworks": True, "careerviet": False,
             "topdev": False, "glints": False, "topcv": False}

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  source VARCHAR, source_job_id VARCHAR,
  url VARCHAR, title_raw VARCHAR, company_raw VARCHAR, location_raw VARCHAR,
  skills_raw VARCHAR, description_raw VARCHAR, posted_date_raw VARCHAR, extra VARCHAR,
  posted_date DATE, first_seen_date DATE, last_seen_date DATE,
  effective_date DATE, date_source VARCHAR,
  is_active BOOLEAN, removed_date DATE, miss_streak INTEGER DEFAULT 0,
  last_streak_run DATE, last_updated TIMESTAMP,
  PRIMARY KEY (source, source_job_id)
);
CREATE TABLE IF NOT EXISTS job_observations (
  source VARCHAR, source_job_id VARCHAR, snapshot_date DATE,
  PRIMARY KEY (source, source_job_id, snapshot_date)
);
"""


def _available_sources() -> list[str]:
    if not BRONZE.exists():
        return []
    return sorted(s.name for s in BRONZE.glob("*")
                  if s.is_dir() and (s / "latest.jsonl").exists())


def _staging_df(source: str, run_date: date) -> pd.DataFrame:
    rows = []
    for line in (BRONZE / source / "latest.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        rows.append({
            "source": r["source"], "source_job_id": str(r["source_job_id"]),
            "url": r.get("url"), "title_raw": r.get("title_raw"),
            "company_raw": r.get("company_raw"), "location_raw": r.get("location_raw"),
            "skills_raw": json.dumps(r.get("skills_raw") or [], ensure_ascii=False),
            "description_raw": r.get("description_raw"),
            "posted_date_raw": r.get("posted_date_raw"),
            "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
            "posted_date": parse_posted_date(r["source"], r.get("posted_date_raw"), run_date),
        })
    return pd.DataFrame(rows)


def upsert_run(run_date: date | None = None, sources: list[str] | None = None) -> dict:
    run_date = run_date or datetime.now().date()
    sources = sources or _available_sources()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(_DDL)
    report = {}

    for src in sources:
        stg = _staging_df(src, run_date)
        if stg.empty:
            continue
        con.register("stg", stg)
        con.execute("SET TimeZone='UTC'")
        # 1) UPSERT master. New rows get first_seen=run_date; existing rows refresh + reactivate.
        con.execute("""
            INSERT INTO jobs BY NAME (
              SELECT *, CAST(? AS DATE) AS first_seen_date, CAST(? AS DATE) AS last_seen_date,
                     TRUE AS is_active, CAST(NULL AS DATE) AS removed_date,
                     0 AS miss_streak, CAST(NULL AS DATE) AS last_streak_run,
                     now() AS last_updated
              FROM stg
            )
            ON CONFLICT (source, source_job_id) DO UPDATE SET
              last_seen_date = excluded.last_seen_date,
              is_active = TRUE, removed_date = NULL, miss_streak = 0,
              url = excluded.url, title_raw = excluded.title_raw,
              company_raw = excluded.company_raw, location_raw = excluded.location_raw,
              skills_raw = excluded.skills_raw, description_raw = excluded.description_raw,
              posted_date_raw = excluded.posted_date_raw, extra = excluded.extra,
              posted_date = COALESCE(jobs.posted_date, excluded.posted_date),
              last_updated = excluded.last_updated
        """, [run_date, run_date])
        n_new = con.execute(
            "SELECT count(*) FROM jobs WHERE source=? AND first_seen_date=? AND last_seen_date=?",
            [src, run_date, run_date]).fetchone()[0]

        # 2) Observations (idempotent via PK).
        con.execute("""INSERT INTO job_observations
            SELECT source, source_job_id, CAST(? AS DATE) FROM stg
            ON CONFLICT DO NOTHING""", [run_date])

        # 3) Removed detection among this source's jobs not seen this run.
        if FULL_SCAN.get(src):
            con.execute("""UPDATE jobs SET is_active=FALSE, removed_date=?
                WHERE source=? AND is_active AND last_seen_date < ?""",
                [run_date, src, run_date])
        else:
            # increment miss_streak once per run_date (idempotent guard), then retire at K.
            con.execute("""UPDATE jobs
                SET miss_streak = miss_streak + 1, last_streak_run = ?
                WHERE source=? AND is_active AND last_seen_date < ?
                  AND (last_streak_run IS NULL OR last_streak_run < ?)""",
                [run_date, src, run_date, run_date])
            con.execute("""UPDATE jobs SET is_active=FALSE, removed_date=?
                WHERE source=? AND is_active AND miss_streak >= ?""",
                [run_date, src, MISS_STREAK_REMOVE])
        n_removed = con.execute(
            "SELECT count(*) FROM jobs WHERE source=? AND removed_date=?",
            [src, run_date]).fetchone()[0]
        con.unregister("stg")
        report[src] = {"seen": len(stg), "new": n_new, "removed_today": n_removed}

    # Safety net: every job gets a usable date. effective_date = site posted_date when
    # available, else first_seen_date (when our pipeline first observed it). date_source
    # records provenance so analysis can treat them differently if needed.
    con.execute("""UPDATE jobs SET
        effective_date = COALESCE(posted_date, first_seen_date),
        date_source = CASE WHEN posted_date IS NOT NULL THEN 'site' ELSE 'first_seen' END""")
    con.close()
    return {"run_date": str(run_date), "per_source": report}


def run_load(run_date_str: str | None = None) -> None:
    run_date = datetime.strptime(run_date_str, "%Y-%m-%d").date() if run_date_str else None
    rep = upsert_run(run_date)
    con = duckdb.connect(str(DB_PATH))
    total, active = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE is_active) FROM jobs").fetchone()
    with_date, with_eff = con.execute(
        "SELECT count(*) FILTER (WHERE posted_date IS NOT NULL), "
        "count(*) FILTER (WHERE effective_date IS NOT NULL) FROM jobs").fetchone()
    print(f"\n{'='*64}\nLOAD → {DB_PATH.name}  (run_date={rep['run_date']})\n{'='*64}")
    print(f"{'source':14s} {'seen':>6s} {'new':>6s} {'removed':>8s}")
    for s, r in rep["per_source"].items():
        print(f"{s:14s} {r['seen']:>6d} {r['new']:>6d} {r['removed_today']:>8d}")
    print(f"\njobs total: {total} | active: {active} | posted_date: {with_date} "
          f"({100*with_date//max(total,1)}%) | effective_date: {with_eff} "
          f"({100*with_eff//max(total,1)}%)")
    # per-source date coverage
    print("\nposted_date coverage by source:")
    for s, c, w in con.execute("""SELECT source, count(*),
            count(*) FILTER (WHERE posted_date IS NOT NULL) FROM jobs GROUP BY source
            ORDER BY source""").fetchall():
        print(f"  {s:14s} {w}/{c}")
    con.close()
    print(f"\nDone. Warehouse: {DB_PATH}")
