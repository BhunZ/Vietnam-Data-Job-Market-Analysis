"""Object storage, and the two ways it can quietly not work.

**A read-only token lists a bucket perfectly well.** R2 API tokens default to read-only, so a
"can we reach the store?" check passes and the first real upload fails. That is a bad place to
find out — it happened here, and it would otherwise have happened inside a scheduled job at six
in the morning. `check_writable` writes, reads back and deletes.

**The store must never become required.** Bronze on R2 is what makes the warehouse rebuildable:
473 of the postings in it no longer exist on any board, so a re-scrape cannot recover them.
That is worth having, and it is still not worth making a cloud account a condition of running
the project. Everything degrades to a no-op without credentials.

These tests use a stub client. They check the logic and the failure modes, not that boto3 can
reach Cloudflare — that is verified by `python -m pipeline sync check` against the real bucket.
"""

import io
from pathlib import Path

import pytest

from pipeline import sync
from pipeline.utils import objstore

R2_VARS = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


@pytest.fixture
def no_store(monkeypatch):
    """A machine with no cloud account — a contributor who just cloned the repository."""
    for var in R2_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def configured(monkeypatch):
    for var in R2_VARS:
        monkeypatch.setenv(var, "x" * 8)
    monkeypatch.setenv("R2_BUCKET", "test-bucket")


# --- configuration -------------------------------------------------------------------

def test_an_unconfigured_store_reports_what_is_missing(no_store):
    assert not objstore.is_configured()
    assert set(objstore.missing_settings()) == set(R2_VARS)


def test_an_empty_bucket_name_counts_as_missing(configured, monkeypatch):
    """The bucket is also the last path segment of the endpoint Cloudflare shows you, which is
    how it ended up set-but-blank here. Blank must not read as configured."""
    monkeypatch.setenv("R2_BUCKET", "   ")
    assert not objstore.is_configured()
    assert "R2_BUCKET" in objstore.missing_settings()


def test_the_endpoint_excludes_the_bucket(configured, monkeypatch):
    """Cloudflare displays the endpoint with the bucket appended; boto3 wants it without, and
    passing the bucket twice yields a 404 that reads like the bucket does not exist."""
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    assert objstore.endpoint() == "https://abc123.r2.cloudflarestorage.com"
    assert "test-bucket" not in objstore.endpoint()


def test_using_the_store_without_credentials_is_a_clear_error(no_store):
    with pytest.raises(objstore.ObjectStoreError, match="not configured"):
        objstore.client()


# --- the read-only token trap --------------------------------------------------------

class _ReadOnlyClient:
    """Lists happily, refuses to write — exactly what a default R2 token does."""

    def get_paginator(self, _):
        class _P:
            def paginate(self, **kw):
                yield {"Contents": [{"Key": "bronze/itviec/2026-06-16.jsonl.gz"}]}
        return _P()

    def put_object(self, **kwargs):
        raise PermissionError("Access Denied")


def test_check_writable_fails_on_a_token_that_can_only_read(configured, monkeypatch):
    monkeypatch.setattr(objstore, "client", lambda: _ReadOnlyClient())
    with pytest.raises(objstore.ObjectStoreError, match="Object Read & Write"):
        objstore.check_writable()


def test_listing_alone_would_have_passed(configured, monkeypatch):
    """The point of the test above: the store looks fine until something is written."""
    monkeypatch.setattr(objstore, "client", lambda: _ReadOnlyClient())
    assert list(objstore.list_keys("bronze/")) == ["bronze/itviec/2026-06-16.jsonl.gz"]


class _RoundTripClient(_ReadOnlyClient):
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(self, Bucket, Key, Body):
        self.store[Key] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.store[Key])}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.store.pop(Key, None)


def test_check_writable_cleans_up_after_itself(configured, monkeypatch):
    stub = _RoundTripClient()
    monkeypatch.setattr(objstore, "client", lambda: stub)
    objstore.check_writable()
    assert stub.deleted == ["_healthcheck/writable"]
    assert not stub.store, "the health-check marker was left in the bucket"


# --- pagination ----------------------------------------------------------------------

def test_listing_follows_pagination(configured, monkeypatch):
    """`list_objects_v2` stops at 1000 keys and does not say so. One snapshot per source per
    day reaches that inside a year, and the missing keys would look like missing history."""
    pages = [{"Contents": [{"Key": f"bronze/a/{i}.gz"}]} for i in range(3)]

    class _Paged:
        def get_paginator(self, _):
            class _P:
                def paginate(self, **kw):
                    yield from pages
            return _P()

    monkeypatch.setattr(objstore, "client", lambda: _Paged())
    assert len(list(objstore.list_keys())) == 3


# --- sync degrades rather than breaks ------------------------------------------------

@pytest.mark.parametrize("call", [
    lambda: sync.push_bronze(),
    lambda: sync.push_gold(),
    lambda: sync.push_warehouse(),
    lambda: sync.pull_bronze(),
    lambda: sync.status(),
])
def test_every_sync_operation_refuses_clearly_without_credentials(no_store, call):
    """Not a crash and not a silent success — the pipeline must stay runnable with no cloud
    account, and a no-op that pretends to have uploaded is worse than an error."""
    with pytest.raises(sync.SyncSkipped, match="not configured"):
        call()


def test_pull_will_not_overwrite_a_local_warehouse_by_default(configured, monkeypatch, tmp_path):
    """A scheduled job pulls before it runs. Replacing a warehouse someone is midway through
    building is not recoverable."""
    warehouse = tmp_path / "warehouse.duckdb"
    warehouse.write_bytes(b"local work in progress")
    monkeypatch.setattr(sync, "WAREHOUSE", warehouse)

    assert sync.pull_warehouse() is None
    assert warehouse.read_bytes() == b"local work in progress"


def test_bronze_keys_mirror_the_local_layout():
    """A bucket listing and a directory listing should be comparable by eye."""
    assert objstore.bronze_key("itviec", "2026-06-16.jsonl.gz") == \
        "bronze/itviec/2026-06-16.jsonl.gz"
