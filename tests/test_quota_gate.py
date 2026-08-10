"""The gate that stops a scrape which cannot finish.

ScraperAPI does not announce an exhausted key — requests simply stop coming back. The run ends
with a partial crawl, and downstream that is indistinguishable from a quiet week: the
ingest-delta gate exists to catch a *flood* of unmatched ids, so a shortfall sails through it.

The loss does not heal. A posting missed this week may be taken down before the next run, and
once a board stops serving it no re-scrape can recover it — 473 of the postings already in the
warehouse are in exactly that state. So the check has to come before anything is spent, not
after.
"""

import pytest

from pipeline import gates


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _accounts(*pairs):
    """Patch requests.get to report (used, limit) for successive keys."""
    responses = [_Response({"requestCount": u, "requestLimit": l}) for u, l in pairs]

    def fake_get(url, params=None, timeout=None):
        return responses.pop(0)

    return fake_get


@pytest.fixture
def two_keys(monkeypatch):
    class _S:
        keys = ["key-a", "key-b"]

    monkeypatch.setattr(gates, "get_secrets", lambda: _S(), raising=False)
    monkeypatch.setattr("pipeline.utils.config.get_secrets", lambda: _S())


def test_a_healthy_budget_passes_and_reports_the_numbers(two_keys, monkeypatch):
    monkeypatch.setattr("requests.get", _accounts((38, 1000), (519, 1000)))
    report = gates.check_scrape_quota(expected=400)

    assert report["checked"] is True
    assert report["remaining"] == 1443
    assert report["expected"] == 400


def test_an_exhausted_budget_stops_the_run(two_keys, monkeypatch):
    monkeypatch.setattr("requests.get", _accounts((980, 1000), (995, 1000)))
    with pytest.raises(gates.QualityGateFailed, match="budget is 25 requests"):
        gates.check_scrape_quota(expected=400)


def test_the_budget_is_the_sum_across_keys(two_keys, monkeypatch):
    """Neither key alone covers a run; together they do. Failing on the first would be wrong."""
    monkeypatch.setattr("requests.get", _accounts((800, 1000), (800, 1000)))
    assert gates.check_scrape_quota(expected=400)["remaining"] == 400


def test_an_overrun_key_never_counts_as_negative_budget(two_keys, monkeypatch):
    """A key past its limit contributes nothing; it must not subtract from the other one."""
    monkeypatch.setattr("requests.get", _accounts((1200, 1000), (100, 1000)))
    assert gates.check_scrape_quota(expected=400)["remaining"] == 900


def test_no_key_configured_is_reported_not_raised(monkeypatch):
    """Someone running the transform steps on existing Bronze has no scraping credentials and
    is doing nothing wrong."""
    class _S:
        keys = []

    monkeypatch.setattr("pipeline.utils.config.get_secrets", lambda: _S())
    report = gates.check_scrape_quota()

    assert report["checked"] is False
    assert "no ScraperAPI key" in report["reason"]


def test_an_unreachable_api_does_not_block_the_pipeline(two_keys, monkeypatch):
    """The check is a safeguard, not a dependency. If ScraperAPI itself is down, that is a
    reason to report and continue — refusing to run would turn their outage into ours."""
    def boom(*args, **kwargs):
        raise ConnectionError("dns")

    monkeypatch.setattr("requests.get", boom)
    report = gates.check_scrape_quota()

    assert report["checked"] is False
    assert "could not reach" in report["reason"]


def test_one_unreachable_key_still_leaves_the_other_counted(two_keys, monkeypatch):
    calls = {"n": 0}

    def half_broken(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("dns")
        return _Response({"requestCount": 100, "requestLimit": 1000})

    monkeypatch.setattr("requests.get", half_broken)
    report = gates.check_scrape_quota(expected=400)

    assert report["checked"] is True
    assert report["remaining"] == 900


def test_the_expected_cost_is_a_real_estimate_not_a_placeholder():
    """Listing pages are re-fetched every run (their cache key carries the run date); detail
    pages are cached forever. A steady run lands well under this, and the margin covers a week
    where a board publishes heavily."""
    assert 200 <= gates.EXPECTED_SCRAPE_REQUESTS <= 800
