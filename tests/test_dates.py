"""Date parsing per source (pipeline/transform/dates.py)."""

from datetime import date

from pipeline.transform.dates import parse_posted_date

RUN = date(2026, 6, 16)


def test_vnw_iso_offset():
    assert parse_posted_date("vietnamworks", "2026-05-28T15:10:39+07:00", RUN) == date(2026, 5, 28)


def test_glints_iso_z():
    assert parse_posted_date("glints", "2026-06-05T07:32:34.028Z", RUN) == date(2026, 6, 5)


def test_topcv_plain():
    assert parse_posted_date("topcv", "2026-06-15", RUN) == date(2026, 6, 15)


def test_topdev_ddmmyyyy():
    assert parse_posted_date("topdev", "12-06-2026", RUN) == date(2026, 6, 12)


def test_careerviet_update_date():
    raw = "Hạn nộp: 30-09-2026 Cập nhật: 09-06-2026"
    assert parse_posted_date("careerviet", raw, RUN) == date(2026, 6, 9)


def test_itviec_relative_days():
    assert parse_posted_date("itviec", "Posted 2 days ago", RUN) == date(2026, 6, 14)


def test_itviec_relative_hours_is_today():
    assert parse_posted_date("itviec", "Posted 3 hours ago", RUN) == RUN


def test_none_returns_none():
    assert parse_posted_date("topdev", None, RUN) is None
