"""Cache policy: listing pages must go stale, detail pages must not.

This is the rule the whole CDC layer rests on. When listing responses were cached
without a date, the second run scored a 100% cache hit, re-reported the first run's
postings, and `first_seen_date` / `miss_streak` / `removed_date` could never move.
"""

import pytest

import pipeline.utils.http as H
from pipeline.utils.config import Secrets
from pipeline.utils.http import ScrapeClient

_NO_SECRETS = Secrets(scraper_api_key=None, scraper_api_key_secondary=None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "RAW_DIR", tmp_path / "raw")
    return ScrapeClient(source="itviec", cfg={}, secrets=_NO_SECRETS, run_date="2026-08-09")


def test_listing_cache_is_keyed_by_run_date(client):
    path = client._cache_path("listing_data-analyst_p1.html", volatile=True)
    assert path.parent.name == "2026-08-09"
    assert path.name == "listing_data-analyst_p1.html"


def test_detail_cache_is_not_keyed_by_run_date(client):
    path = client._cache_path("detail_12345.html")
    assert path.parent.name == "itviec"


def test_a_later_run_does_not_hit_yesterdays_listing_cache(client, tmp_path, monkeypatch):
    """The whole point: tomorrow's run must go back to the network for listings."""
    today = client._cache_path("listing_x_p1.html", volatile=True)
    today.parent.mkdir(parents=True, exist_ok=True)
    today.write_text("yesterday's postings", encoding="utf-8")

    tomorrow = ScrapeClient(source="itviec", cfg={}, secrets=client.secrets,
                            run_date="2026-08-16")
    assert tomorrow._cache_path("listing_x_p1.html", volatile=True) != today
    assert not tomorrow._cache_path("listing_x_p1.html", volatile=True).exists()


def test_a_later_run_still_hits_the_detail_cache(client):
    """Detail pages are the expensive ones; a rollover must not re-buy them."""
    detail = client._cache_path("detail_999.html")
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text("a job description", encoding="utf-8")

    tomorrow = ScrapeClient(source="itviec", cfg={}, secrets=client.secrets,
                            run_date="2026-08-16")
    assert tomorrow._cache_path("detail_999.html") == detail
    assert tomorrow._cache_path("detail_999.html").exists()


def test_every_listing_call_site_passes_volatile():
    """Guards against a new connector quietly reintroducing the frozen-crawler bug.

    Rule: a `client.fetch(...)` outside `fetch_detail` is a listing fetch and must pass
    `volatile=True`. Every detail fetch in the codebase lives inside a `fetch_detail`
    method, which makes that a reliable way to tell the two apart.
    """
    import ast
    import inspect

    from pipeline.ingest import CONNECTORS

    missing = []
    for name, cls in CONNECTORS.items():
        module = inspect.getmodule(cls)
        tree = ast.parse(inspect.getsource(module))

        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef) or func.name == "fetch_detail":
                continue
            for node in ast.walk(func):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "fetch"):
                    kwargs = {kw.arg for kw in node.keywords}
                    if "volatile" not in kwargs:
                        missing.append(f"{name}.{func.name}:{node.lineno}")

    assert missing == [], f"listing fetches missing volatile=True: {missing}"
