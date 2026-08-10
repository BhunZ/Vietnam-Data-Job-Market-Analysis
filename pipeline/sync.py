"""Move the warehouse and the Bronze history between this machine and object storage.

Bronze snapshots are the only record of what each board displayed on a given day. Once a
posting is taken down the board stops serving it, so a re-scrape cannot recover it — 473 of
the 3,951 postings here are already in that state. Until now that record existed on one disk,
which means the project had no way back from a lost laptop and no way for a second machine to
pick up where the first left off.

Three things move, and they are not equally precious:

* **Bronze** is the source of truth. Snapshots are named by date and never rewritten, so upload
  skips anything already present rather than overwriting it. Losing this loses history.
* **Gold** is published as Parquet so it can be read without downloading anything —
  `read_parquet('r2://<bucket>/gold/<table>.parquet')` in DuckDB queries it in place. Storage
  and compute stay separate, which is the same shape as Athena over S3.
* **warehouse.duckdb** is a convenience copy. It is derived, it is 26 MB, and it can be rebuilt
  from Bronze. It travels so a fresh clone can start querying immediately, not because it
  matters.

Everything degrades to a no-op when the store is unconfigured. A contributor without a cloud
account must still be able to run the whole chain.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from .utils import bronze, objstore
from .utils.config import DATA_DIR

logger = logging.getLogger(__name__)

WAREHOUSE = DATA_DIR / "warehouse.duckdb"

#: Published to R2 as Parquet on every push. These are the serving tables — the ones a reader
#: would query — not the intermediate ones.
GOLD_TABLES = [
    "gold_jobs", "gold_market_share", "gold_family_skill", "gold_company",
    "gold_location", "gold_seniority", "gold_skill_cooccurrence", "gold_domain_share",
]


class SyncSkipped(RuntimeError):
    """Raised when a sync was asked for but no store is configured."""


def _require_store() -> None:
    if not objstore.is_configured():
        raise SyncSkipped(
            "object store is not configured; missing "
            f"{', '.join(objstore.missing_settings())}. "
            "Everything still works locally — set the R2_* variables to enable sync.")


# ----------------------------------------------------------------------------------
# Push
# ----------------------------------------------------------------------------------

def push_bronze(force: bool = False) -> tuple[int, int]:
    """Upload Bronze snapshots. Returns (uploaded, skipped).

    A snapshot is immutable: `2026-08-09.jsonl.gz` for a given source is what that board showed
    that day and is never legitimately different. Already-present keys are skipped rather than
    re-sent, so a repeated push costs one HEAD per file instead of the whole history.
    """
    _require_store()
    uploaded = skipped = 0
    for source in bronze.available_sources():
        for path in bronze.list_snapshots(source):
            key = objstore.bronze_key(source, path.name)
            if not force and objstore.exists(key):
                skipped += 1
                continue
            objstore.put_file(path, key)
            uploaded += 1
    logger.info("bronze push: %d uploaded, %d already present", uploaded, skipped)
    return uploaded, skipped


def push_gold() -> int:
    """Export the serving tables to Parquet and upload them. Returns the number published.

    zstd because these are read far more often than written, and a smaller object is a faster
    range read for a client that only wants two columns.
    """
    _require_store()
    if not WAREHOUSE.exists():
        raise SyncSkipped(f"no warehouse at {WAREHOUSE} — run the pipeline first")

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    present = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'").fetchall()}
    published = 0
    try:
        for table in GOLD_TABLES:
            if table not in present:
                logger.warning("gold table %s is not in the warehouse — skipping", table)
                continue
            tmp = DATA_DIR / f".{table}.parquet"
            con.execute(
                f"copy (select * from {table}) to '{tmp.as_posix()}' "
                f"(format parquet, compression zstd)")
            try:
                objstore.put_file(tmp, f"gold/{table}.parquet")
                published += 1
            finally:
                tmp.unlink(missing_ok=True)
    finally:
        con.close()
    logger.info("gold push: %d tables published as Parquet", published)
    return published


def push_warehouse() -> int:
    """Upload the DuckDB file itself. Returns bytes sent."""
    _require_store()
    if not WAREHOUSE.exists():
        raise SyncSkipped(f"no warehouse at {WAREHOUSE}")
    return objstore.put_file(WAREHOUSE, objstore.WAREHOUSE_KEY)


# ----------------------------------------------------------------------------------
# Pull
# ----------------------------------------------------------------------------------

def pull_warehouse(overwrite: bool = False) -> int | None:
    """Download the warehouse. Returns bytes, or None if a local copy was kept.

    Refuses to clobber an existing file unless asked. A scheduled job pulls before it runs, and
    silently replacing a warehouse someone was midway through building is not recoverable.
    """
    _require_store()
    if WAREHOUSE.exists() and not overwrite:
        logger.info("keeping the local warehouse; pass overwrite=True to replace it")
        return None
    if not objstore.exists(objstore.WAREHOUSE_KEY):
        raise SyncSkipped(f"no warehouse in the bucket at {objstore.WAREHOUSE_KEY}")
    return objstore.get_file(objstore.WAREHOUSE_KEY, WAREHOUSE)


def pull_bronze() -> tuple[int, int]:
    """Download every Bronze snapshot that is not already local. Returns (downloaded, skipped).

    This is the recovery path: with the bucket and this function, a machine holding nothing can
    rebuild the warehouse from raw, including the postings the boards have since removed.
    """
    _require_store()
    downloaded = skipped = 0
    prefix = objstore.BRONZE_PREFIX + "/"
    for key in objstore.list_keys(prefix):
        rel = key[len(prefix):]
        if "/" not in rel:
            continue
        source, filename = rel.split("/", 1)
        local = bronze.source_dir(source) / filename
        if local.exists():
            skipped += 1
            continue
        objstore.get_file(key, local)
        downloaded += 1
    logger.info("bronze pull: %d downloaded, %d already local", downloaded, skipped)
    return downloaded, skipped


def status() -> dict:
    """What is in the bucket, without downloading any of it."""
    _require_store()
    keys = list(objstore.list_keys())
    bronze_keys = [k for k in keys if k.startswith(objstore.BRONZE_PREFIX + "/")]
    sources = sorted({k.split("/")[1] for k in bronze_keys if k.count("/") >= 2})
    return {
        "bucket": objstore.bucket(),
        "objects": len(keys),
        "bronze_snapshots": len(bronze_keys),
        "bronze_sources": sources,
        "gold_tables": sorted(k.split("/")[-1] for k in keys if k.startswith("gold/")),
        "warehouse": objstore.exists(objstore.WAREHOUSE_KEY),
    }
