"""The `all` chain (pipeline/__main__.py).

`all` was a stub that printed "not implemented yet" and exited 1 while the module
docstring advertised it as running the whole pipeline. What matters now is that it runs
the steps in the right order, stops at the first failure instead of carrying on, and
tells you how to resume.
"""

import pytest

import pipeline.__main__ as M
import pipeline.utils.runlog as R


@pytest.fixture(autouse=True)
def _isolate_runlog(tmp_path, monkeypatch):
    """`_run_all` records every step, so point the log at a temp warehouse.

    Without this the suite writes its fake chains into the real data/warehouse.duckdb —
    which it did once, and the run history then showed a fifteen-step run that never
    happened.
    """
    monkeypatch.setattr(R, "DB_PATH", tmp_path / "wh.duckdb")
    monkeypatch.setattr(R, "_run_id", None)
    monkeypatch.delenv(R.RUN_ID_ENV, raising=False)


def _args(**kw):
    defaults = dict(command="all", from_step=None, skip=[], dry_run=False,
                    allow_large_delta=False, run_date="2026-08-09", jd_limit=25,
                    verbose=False)
    defaults.update(kw)
    return type("Args", (), defaults)()


def test_the_gate_sits_between_load_and_label():
    """Labeling is what costs quota, so the parser check has to come before it."""
    steps = M.ALL_STEPS
    assert steps.index("load") < steps.index("gate") < steps.index("label")


def test_validate_is_last():
    assert M.ALL_STEPS[-1] == "validate"


def test_dry_run_lists_every_step_and_runs_nothing(capsys, monkeypatch):
    monkeypatch.setattr(M, "_run_one", lambda *a: pytest.fail("dry run must not execute"))

    assert M._run_all(_args(dry_run=True)) == 0
    assert "scrape" in capsys.readouterr().out


def test_from_skips_everything_before_it(capsys, monkeypatch):
    monkeypatch.setattr(M, "_run_one", lambda *a: pytest.fail("dry run must not execute"))

    M._run_all(_args(dry_run=True, from_step="silver"))

    out = capsys.readouterr().out
    assert "silver" in out and "scrape" not in out and "load" not in out


def test_unknown_step_names_are_rejected_rather_than_ignored(capsys):
    assert M._run_all(_args(from_step="nonsense")) == 1
    assert M._run_all(_args(skip=["nonsense"])) == 1


def test_the_chain_stops_at_the_first_failure(capsys, monkeypatch):
    ran = []

    def fake(step, args, run_date):
        ran.append(step)
        return 1 if step == "gate" else 0

    monkeypatch.setattr(M, "_run_one", fake)

    assert M._run_all(_args()) == 1
    assert ran == ["scrape", "load", "gate"]  # silver onwards never started
    assert "--from gate" in capsys.readouterr().out


def test_an_exception_stops_the_chain_without_a_traceback(capsys, monkeypatch):
    from pipeline.gates import QualityGateFailed

    def fake(step, args, run_date):
        if step == "gate":
            raise QualityGateFailed("parser looks broken")
        return 0

    monkeypatch.setattr(M, "_run_one", fake)

    assert M._run_all(_args()) == 1
    out = capsys.readouterr().out
    assert "parser looks broken" in out
    assert "--from gate" in out


def test_all_steps_share_one_run_id(monkeypatch):
    import duckdb

    seen = []
    monkeypatch.setattr(M, "_run_one", lambda step, a, d: seen.append(step) or 0)

    assert M._run_all(_args(skip=["scrape"])) == 0
    assert len(seen) == len(M.ALL_STEPS) - 1

    con = duckdb.connect(str(R.DB_PATH), read_only=True)
    try:
        run_ids = con.execute("SELECT DISTINCT run_id FROM pipeline_runs").fetchall()
        n_steps = con.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0]
    finally:
        con.close()

    # One id covering the whole chain is what makes `GROUP BY run_id` mean "one execution".
    assert len(run_ids) == 1
    assert n_steps == len(M.ALL_STEPS) - 1
