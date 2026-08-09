"""Run history: one row per pipeline step, in the warehouse itself.

The question this exists to answer is "did last night's run go through, and what did
it move?" — which nothing in the project could answer before. Steps printed to stdout
and stdout is gone the moment the terminal closes.

Layout::

    pipeline_runs(step_run_id, run_id, step, started_at, ended_at, duration_s,
                  rows_in, rows_out, status, error_msg)

`run_id` groups the steps of one execution, so `pipeline all` produces nine rows sharing
an id while a hand-run `pipeline silver` produces one row with an id of its own. It is
taken from the ``PIPELINE_RUN_ID`` environment variable when set, which is how `all`
hands the same id to every step, and generated once per process otherwise.

Usage::

    with runlog.track("silver"):
        ...
        runlog.set_rows(rows_in=1701, rows_out=1554)

A row lands at *start* with ``status='running'``, then gets updated on the way out. That
ordering is deliberate: if the process is killed mid-step, the row stays `running`
forever, and a stuck `running` row is exactly the signal you want. A step that only
recorded itself on success would leave no trace of the run that died.

Nothing here is allowed to break a pipeline. Every write is wrapped: if the warehouse is
locked or the disk is full, logging degrades to a warning and the step carries on.
Monitoring that can take down the thing it monitors is worse than no monitoring.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime

import duckdb

from .config import DATA_DIR

log = logging.getLogger("pipeline.runlog")

DB_PATH = DATA_DIR / "warehouse.duckdb"
RUN_ID_ENV = "PIPELINE_RUN_ID"

_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
  step_run_id VARCHAR PRIMARY KEY,
  run_id      VARCHAR,
  step        VARCHAR,
  started_at  TIMESTAMP,
  ended_at    TIMESTAMP,
  duration_s  DOUBLE,
  rows_in     BIGINT,
  rows_out    BIGINT,
  status      VARCHAR,   -- running | ok | failed
  error_msg   VARCHAR
);
"""

_run_id: str | None = None


class _Step:
    """Handle for the step currently being tracked. Counts are optional."""

    def __init__(self, step_run_id: str, step: str) -> None:
        self.step_run_id = step_run_id
        self.step = step
        self.rows_in: int | None = None
        self.rows_out: int | None = None


_active: _Step | None = None


def new_run_id() -> str:
    """An id that sorts chronologically and is still unique within a second."""
    return f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def current_run_id() -> str:
    """Run id for this process, creating and exporting one on first use.

    Exporting it means a step launched as a subprocess joins the same run rather than
    inventing its own.
    """
    global _run_id
    if _run_id is None:
        _run_id = os.environ.get(RUN_ID_ENV) or new_run_id()
        os.environ[RUN_ID_ENV] = _run_id
    return _run_id


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(_DDL)
    return con


def set_rows(rows_in: int | None = None, rows_out: int | None = None) -> None:
    """Attach row counts to the step in progress. No-op outside a `track` block,
    so steps can call it unconditionally."""
    if _active is None:
        return
    if rows_in is not None:
        _active.rows_in = int(rows_in)
    if rows_out is not None:
        _active.rows_out = int(rows_out)


@contextmanager
def track(step: str):
    """Record one step: start, finish, row counts, and how it ended."""
    global _active

    step_run_id = uuid.uuid4().hex
    handle = _Step(step_run_id, step)
    started = datetime.now()

    try:
        con = _connect()
        con.execute(
            "INSERT INTO pipeline_runs (step_run_id, run_id, step, started_at, status) "
            "VALUES (?, ?, ?, ?, 'running')",
            [step_run_id, current_run_id(), step, started])
        con.close()
    except Exception as exc:  # noqa: BLE001 — logging must never break the pipeline
        log.warning("run log unavailable at start of %s: %s", step, exc)

    prev, _active = _active, handle
    status, error = "ok", None
    try:
        yield handle
    except BaseException as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        _active = prev
        ended = datetime.now()
        try:
            con = _connect()
            con.execute(
                "UPDATE pipeline_runs SET ended_at=?, duration_s=?, rows_in=?, rows_out=?, "
                "status=?, error_msg=? WHERE step_run_id=?",
                [ended, (ended - started).total_seconds(),
                 handle.rows_in, handle.rows_out, status, error, step_run_id])
            con.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("run log unavailable at end of %s: %s", step, exc)


def recent(limit: int = 20) -> list[tuple]:
    """Most recent step rows, newest first. Empty when nothing has been recorded yet."""
    if not DB_PATH.exists():
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(
            "SELECT run_id, step, started_at, duration_s, rows_in, rows_out, status, error_msg "
            "FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", [limit]).fetchall()
    except duckdb.CatalogException:  # table not created yet
        return []
    finally:
        con.close()


def print_recent(limit: int = 20) -> None:
    rows = recent(limit)
    if not rows:
        print("pipeline_runs is empty — no step has been recorded yet.")
        return
    print(f"\n{'='*100}\nPIPELINE RUNS (newest first)\n{'='*100}")
    print(f"{'run_id':22s} {'step':14s} {'started':20s} {'secs':>7s} "
          f"{'in':>7s} {'out':>7s} {'status':8s}")
    for run_id, step, started, dur, r_in, r_out, status, err in rows:
        print(f"{run_id:22s} {step:14s} {str(started)[:19]:20s} "
              f"{(f'{dur:.1f}' if dur is not None else '-'):>7s} "
              f"{(str(r_in) if r_in is not None else '-'):>7s} "
              f"{(str(r_out) if r_out is not None else '-'):>7s} {status:8s}")
        if err:
            print(f"{'':22s} └─ {err}")
    print()
