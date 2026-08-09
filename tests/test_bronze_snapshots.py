"""Bronze layout guarantees (pipeline/utils/bronze.py).

The property that matters: a run never destroys an earlier run's raw data. Everything
else here — gzip, the pointer file, legacy fallback — exists to serve that or to keep
snapshots written before the change readable.
"""

import gzip
import json

import pytest

import pipeline.utils.bronze as B


@pytest.fixture(autouse=True)
def _tmp_bronze(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "BRONZE_DIR", tmp_path / "bronze")
    return tmp_path / "bronze"


def _rows(*ids):
    return [json.dumps({"source_job_id": i, "description_raw": ""}) for i in ids]


def test_a_second_run_does_not_overwrite_the_first():
    B.write_snapshot("itviec", "2026-01-01", _rows("a", "b"))
    B.write_snapshot("itviec", "2026-01-02", _rows("a", "c"))

    first = B.snapshot_path("itviec", "2026-01-01")
    assert first.is_file()
    assert {r["source_job_id"] for r in B.iter_rows(first)} == {"a", "b"}
    assert len(B.list_snapshots("itviec")) == 2


def test_latest_points_at_the_newest_snapshot():
    B.write_snapshot("itviec", "2026-01-01", _rows("a"))
    B.write_snapshot("itviec", "2026-01-03", _rows("a", "b"))
    B.write_snapshot("itviec", "2026-01-02", _rows("zzz"))  # written out of order

    # The pointer follows write order, not date order: it names the last run to finish.
    assert B.latest_path("itviec").name == "2026-01-02.jsonl.gz"
    assert {r["source_job_id"] for r in B.read_latest("itviec")} == {"zzz"}


def test_snapshots_are_gzipped_and_readable_as_gzip():
    path = B.write_snapshot("itviec", "2026-01-01", _rows("a"))
    assert path.suffix == ".gz"
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        assert json.loads(fh.readline())["source_job_id"] == "a"


def test_plain_jsonl_snapshots_still_load():
    """Snapshots written before gzip landed must keep working."""
    path = B.write_snapshot("itviec", "2026-01-01", _rows("a"), compressed=False)
    assert path.name == "2026-01-01.jsonl"
    assert {r["source_job_id"] for r in B.read_latest("itviec")} == {"a"}


def test_legacy_latest_jsonl_is_read_when_no_dated_snapshot_exists(_tmp_bronze):
    d = _tmp_bronze / "careerviet"
    d.mkdir(parents=True)
    (d / "latest.jsonl").write_text("\n".join(_rows("old1", "old2")), encoding="utf-8")

    assert B.latest_path("careerviet").name == "latest.jsonl"
    assert {r["source_job_id"] for r in B.read_latest("careerviet")} == {"old1", "old2"}
    assert "careerviet" in B.available_sources()


def test_sample_jsonl_is_not_mistaken_for_a_snapshot(_tmp_bronze):
    """`inspect` drops sample.jsonl in the same directory; it is not a run."""
    d = _tmp_bronze / "itviec"
    d.mkdir(parents=True)
    (d / "sample.jsonl").write_text("\n".join(_rows("sample")), encoding="utf-8")

    assert B.list_snapshots("itviec") == []
    assert B.latest_path("itviec") is None


def test_available_sources_skips_empty_directories(_tmp_bronze):
    (_tmp_bronze / "glints").mkdir(parents=True)
    B.write_snapshot("itviec", "2026-01-01", _rows("a"))

    assert B.available_sources() == ["itviec"]


def test_interrupted_write_leaves_no_temp_file_behind():
    B.write_snapshot("itviec", "2026-01-01", _rows("a"))
    leftovers = [p.name for p in B.source_dir("itviec").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_rewrite_latest_updates_in_place_without_adding_a_snapshot():
    """`enrich` fills JD on the newest snapshot — that is an update, not a new run."""
    B.write_snapshot("itviec", "2026-01-01", _rows("a", "b"))
    enriched = [json.dumps({"source_job_id": i, "description_raw": "JD text"})
                for i in ("a", "b")]
    B.rewrite_latest("itviec", enriched)

    assert len(B.list_snapshots("itviec")) == 1
    assert all(r["description_raw"] == "JD text" for r in B.read_latest("itviec"))


def test_rewrite_latest_refuses_when_there_is_nothing_to_enrich():
    with pytest.raises(FileNotFoundError):
        B.rewrite_latest("itviec", _rows("a"))


def test_prune_keeps_the_newest_n():
    for day in ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"):
        B.write_snapshot("itviec", day, _rows("a"))

    deleted = B.prune("itviec", keep=2)

    assert [p.name for p in deleted] == ["2026-01-01.jsonl.gz", "2026-01-02.jsonl.gz"]
    assert [p.name for p in B.list_snapshots("itviec")] == [
        "2026-01-03.jsonl.gz", "2026-01-04.jsonl.gz"]
