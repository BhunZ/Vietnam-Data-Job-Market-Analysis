"""Run history semantics (pipeline/utils/runlog.py).

Two properties carry the weight. A step that dies must leave evidence, and the logger
must never be the reason a step dies.
"""

import duckdb
import pandas as pd
import pytest

import pipeline.utils.runlog as R


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "wh.duckdb"
    monkeypatch.setattr(R, "DB_PATH", db)
    monkeypatch.setattr(R, "_run_id", None)
    monkeypatch.delenv(R.RUN_ID_ENV, raising=False)
    return db


def _rows(db, sql="SELECT * FROM pipeline_runs"):
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql).fetchdf().to_dict("records")
    finally:
        con.close()


def test_a_successful_step_is_recorded_with_its_row_counts(_tmp_db):
    with R.track("silver"):
        R.set_rows(rows_in=1701, rows_out=1554)

    (row,) = _rows(_tmp_db)
    assert row["step"] == "silver"
    assert row["status"] == "ok"
    assert (row["rows_in"], row["rows_out"]) == (1701, 1554)
    assert row["duration_s"] >= 0
    assert row["ended_at"] is not None


def test_a_failing_step_is_recorded_and_the_error_still_propagates(_tmp_db):
    with pytest.raises(ValueError, match="parser broke"):
        with R.track("load"):
            raise ValueError("parser broke")

    (row,) = _rows(_tmp_db)
    assert row["status"] == "failed"
    assert "ValueError: parser broke" in row["error_msg"]
    assert row["ended_at"] is not None


def test_steps_of_one_process_share_a_run_id(_tmp_db):
    with R.track("load"):
        pass
    with R.track("silver"):
        pass

    run_ids = {r["run_id"] for r in _rows(_tmp_db)}
    assert len(run_ids) == 1


def test_an_inherited_run_id_is_honoured(_tmp_db, monkeypatch):
    monkeypatch.setenv(R.RUN_ID_ENV, "20260809T120000-abcdef")
    with R.track("gold"):
        pass

    (row,) = _rows(_tmp_db)
    assert row["run_id"] == "20260809T120000-abcdef"


def test_a_killed_step_leaves_a_running_row(_tmp_db):
    """The start row lands before the work, so a crash is visible as a stuck 'running'."""
    with R.track("label") as handle:
        (row,) = _rows(_tmp_db)
        assert row["status"] == "running"
        assert pd.isna(row["ended_at"])  # pandas renders a SQL NULL timestamp as NaT
        assert handle.step == "label"


def test_logging_failure_does_not_break_the_step(_tmp_db, monkeypatch):
    """A locked or unwritable warehouse must degrade to a warning, not an exception."""
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(R, "_connect", boom)

    ran = False
    with R.track("gold"):
        ran = True
    assert ran is True


def test_set_rows_outside_a_step_is_a_no_op():
    R.set_rows(rows_in=5, rows_out=5)  # must not raise


def test_recent_is_empty_before_anything_runs(_tmp_db):
    assert R.recent() == []


def test_recent_returns_newest_first(_tmp_db):
    for step in ("load", "silver", "gold"):
        with R.track(step):
            pass

    assert [r[1] for r in R.recent()] == ["gold", "silver", "load"]
