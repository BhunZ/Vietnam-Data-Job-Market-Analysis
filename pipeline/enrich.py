"""JD enrichment: fill `description_raw` on an existing Bronze file by fetching each
posting's detail (per-source `fetch_detail`). Resumable — detail responses are cached and
already-enriched rows are skipped, and the Bronze file is flushed periodically.

Run:  python -m pipeline enrich --source careerviet [--delay 2] [--limit N]
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .ingest import CONNECTORS
from .models import BronzeJob
from .utils import bronze

log = logging.getLogger("pipeline.enrich")


def _write(rows: list[BronzeJob], source: str) -> Path:
    # Fills JD on the newest snapshot in place: these are the same observations with
    # more detail, not a new run. See pipeline/utils/bronze.py.
    return bronze.rewrite_latest(source, (r.model_dump_json() for r in rows))


def run_enrich(source: str, delay: float | None = None, limit: int | None = None,
               max_live_fetches: int = 1000, flush_every: int = 25) -> None:
    path = bronze.latest_path(source)
    if path is None:
        print(f"No bronze snapshot for {source} ({bronze.source_dir(source)}).")
        return
    rows = [BronzeJob.model_validate(r) for r in bronze.iter_rows(path)]
    conn = CONNECTORS[source]()
    conn.client.max_live_fetches = max_live_fetches
    if delay is not None:  # shorter, still-polite delay for bulk detail fetching
        conn.client.cfg["min_delay_seconds"] = delay
        conn.client.cfg["max_delay_seconds"] = max(delay, delay + 1)
    if not hasattr(conn, "fetch_detail"):
        print(f"{source} has no fetch_detail (JD already inline?). Nothing to do.")
        return

    todo = [r for r in rows if not r.description_raw]
    if limit:
        todo = todo[:limit]
    print(f"{source}: {len(rows)} rows, {len(todo)} missing JD "
          f"(delay={delay or 'default'})")

    done = 0
    for r in todo:
        before = bool(r.description_raw)
        conn.fetch_detail(r)
        if r.description_raw and not before:
            done += 1
        if done and done % flush_every == 0:
            _write(rows, source)
            print(f"  ... {done}/{len(todo)} enriched (flushed)")
    path = _write(rows, source)

    have = sum(1 for r in rows if r.description_raw)
    print(f"DONE {source}: JD coverage {have}/{len(rows)} "
          f"({100*have/len(rows):.0f}%). Bronze: {path}")
