"""Browser-captured TopCV import (pipeline/topcv_browser_listing.py).

TopCV is fetched by hand because DataDome blocks the pipeline's HTTP client. The import
still has to produce a Bronze snapshot indistinguishable from a connector's, or everything
downstream would need a special case for it.
"""

import json

import pytest

import pipeline.topcv_browser_listing as T
import pipeline.utils.bronze as B


@pytest.fixture(autouse=True)
def _tmp_bronze(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "BRONZE_DIR", tmp_path / "bronze")
    return tmp_path


def _payload(tmp_path, categories, captured_at="2026-08-09"):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps({"captured_at": captured_at, "categories": categories}),
                    encoding="utf-8")
    return path


def test_a_capture_becomes_a_bronze_snapshot_like_any_other_source(_tmp_bronze):
    path = _payload(_tmp_bronze, {
        "data-engineer": [{"job_id": "2204367", "title": "Kỹ Sư Dữ Liệu",
                           "company": "VIETTEL", "city": "Hà Nội"}],
        "data-analyst": [{"job_id": "2257507", "title": "Business Data Analyst",
                          "company": "I-KONECT", "city": "Hồ Chí Minh"}],
    })

    report = T.run_import(path)

    assert report["distinct"] == 2
    rows = B.read_latest("topcv")
    assert {r["source"] for r in rows} == {"topcv"}
    assert {r["source_job_id"] for r in rows} == {"2204367", "2257507"}
    assert B.latest_path("topcv").name == "2026-08-09.jsonl.gz"


def test_the_capture_date_names_the_snapshot(_tmp_bronze):
    path = _payload(_tmp_bronze, {"etl": [{"job_id": "1", "title": "ETL Developer"}]},
                    captured_at="2026-07-01")

    assert T.run_import(path)["run_date"] == "2026-07-01"
    assert B.latest_path("topcv").name == "2026-07-01.jsonl.gz"


def test_an_explicit_run_date_wins_over_the_captured_one(_tmp_bronze):
    path = _payload(_tmp_bronze, {"etl": [{"job_id": "1", "title": "ETL Developer"}]},
                    captured_at="2026-07-01")

    assert T.run_import(path, run_date="2026-08-09")["run_date"] == "2026-08-09"


def test_a_posting_listed_under_two_categories_is_stored_once(_tmp_bronze):
    path = _payload(_tmp_bronze, {
        "data-engineer": [{"job_id": "99", "title": "Data Engineer"}],
        "big-data": [{"job_id": "99", "title": "Data Engineer"}],
    })

    report = T.run_import(path)

    assert report["distinct"] == 1
    assert len(B.read_latest("topcv")) == 1


def test_records_without_an_id_or_title_are_skipped_not_stored(_tmp_bronze):
    path = _payload(_tmp_bronze, {"etl": [
        {"job_id": "1", "title": "ETL Developer"},
        {"job_id": "", "title": "no id"},
        {"job_id": "3", "title": ""},
        {"company": "no id and no title"},
    ]})

    report = T.run_import(path)

    assert (report["distinct"], report["skipped"]) == (1, 3)


def test_provenance_is_recorded_so_these_rows_stay_distinguishable(_tmp_bronze):
    path = _payload(_tmp_bronze, {"etl": [{"job_id": "1", "title": "ETL Developer"}]})

    T.run_import(path)

    (row,) = B.read_latest("topcv")
    assert row["extra"]["captured_via"] == "browser"
    assert row["extra"]["category_seen_in"] == ["etl"]


def test_an_empty_capture_fails_loudly_rather_than_writing_nothing(_tmp_bronze):
    """A silent empty snapshot would read downstream as 'TopCV had no jobs today'."""
    path = _payload(_tmp_bronze, {"etl": []})

    with pytest.raises(ValueError, match="no usable postings"):
        T.run_import(path)

    assert B.latest_path("topcv") is None
