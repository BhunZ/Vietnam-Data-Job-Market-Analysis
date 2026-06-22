"""Parse each source's raw posted-date into an ISO `date`.

Most sources give an absolute timestamp; ITviec only gives a relative string ("Posted N
days ago") so we derive it from the run date; TopDev exposes no date (caller falls back to
`first_seen_date`). Returns a `datetime.date` or None.

This distinguishes `posted_date` (what the site states) from `first_seen_date` (when our
pipeline first observed the job) — both are tracked in the warehouse.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_CV_UPDATE = re.compile(r"Cập nhật:\s*(\d{2})-(\d{2})-(\d{4})")  # "Cập nhật: DD-MM-YYYY"
_ITV_REL = re.compile(r"(\d+)\s*(minute|hour|day|week|month|year)", re.I)


def _from_iso(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:  # noqa: BLE001
        return None


def _itviec_relative(s: str, run_date: date) -> date | None:
    m = _ITV_REL.search(s)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {
        "minute": timedelta(0), "hour": timedelta(0), "day": timedelta(days=n),
        "week": timedelta(weeks=n), "month": timedelta(days=30 * n),
        "year": timedelta(days=365 * n),
    }[unit]
    return run_date - delta


def parse_posted_date(source: str, posted_date_raw: str | None, run_date: date) -> date | None:
    """Return the posting date for a row, or None if the source provides none."""
    if not posted_date_raw:
        return None
    s = posted_date_raw.strip()
    if source in ("vietnamworks", "glints", "topcv"):
        return _from_iso(s)
    if source == "careerviet":
        m = _CV_UPDATE.search(s)
        if m:
            d, mo, y = map(int, m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return None
        return None
    if source == "itviec":
        return _itviec_relative(s, run_date)
    if source == "topdev":  # published.date = "DD-MM-YYYY"
        m = re.match(r"(\d{2})-(\d{2})-(\d{4})", s)
        if m:
            d, mo, y = map(int, m.groups())
            try:
                return date(y, mo, d)
            except ValueError:
                return None
        return None
    return _from_iso(s)
