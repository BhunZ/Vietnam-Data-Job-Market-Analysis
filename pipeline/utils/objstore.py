"""Object storage for Bronze snapshots and the warehouse — S3-compatible, currently R2.

Two problems this solves, and they are different sizes.

The small one: `data/warehouse.duckdb` is 26 MB and lives in git. Every rebuild rewrites the
whole binary, so the repository grows by another copy each time and `git clone` gets slower
forever. Binaries do not diff.

The large one: **the warehouse cannot currently be rebuilt.** Bronze snapshots are the raw
record of what each board showed on each day, and they only exist on one laptop. If that disk
dies, the postings that have since been taken down are gone — no re-scrape can recover them,
because the boards no longer serve them. A landing zone that exists in one place is not a
landing zone, it is a cache.

**R2 rather than S3.** The account already exists here for Workers AI, the free tier is 10 GB,
and egress is not billed — which matters because rebuilding pulls the whole Bronze history back
down. The API is S3's, so this module is boto3 and would point at AWS by changing one URL.

**Optional by design.** Nothing here is required to run the pipeline. `is_configured()` is false
when the credentials are absent, and every caller falls back to local-only behaviour. A
contributor who clones the repository must be able to run the whole chain without a cloud
account; making the pipeline depend on one would trade a small problem for a larger one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

#: Everything needed to talk to the bucket. `R2_BUCKET` is easy to leave empty — the value is
#: also the last path segment of the S3 endpoint Cloudflare shows you, which is how it ended up
#: blank here once.
_REQUIRED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")

#: Where each kind of artifact lives in the bucket.
BRONZE_PREFIX = "bronze"
WAREHOUSE_KEY = "warehouse/warehouse.duckdb"


class ObjectStoreError(RuntimeError):
    """Raised when the store is asked to do something it cannot."""


def missing_settings() -> list[str]:
    """Which of the required variables are absent or empty."""
    return [k for k in _REQUIRED if not (os.getenv(k) or "").strip()]


def is_configured() -> bool:
    """True when a bucket can be reached. Callers treat False as "stay local", not as an error."""
    return not missing_settings()


def endpoint() -> str:
    """R2's S3 endpoint is derived from the account id, so it is not a separate secret.

    Cloudflare's dashboard shows an endpoint with the bucket appended; boto3 wants it without,
    and passing the bucket twice produces a 404 that reads like the bucket does not exist.
    """
    return f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def bucket() -> str:
    return os.environ["R2_BUCKET"]


def client():
    """A boto3 S3 client pointed at the bucket.

    Imported lazily: boto3 is only needed when the store is actually used, and the pipeline must
    install and run without it.
    """
    if not is_configured():
        raise ObjectStoreError(
            f"object store is not configured; missing {', '.join(missing_settings())}")
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise ObjectStoreError(
            "boto3 is not installed — `pip install -r requirements.lock`") from exc

    return boto3.client(
        "s3",
        endpoint_url=endpoint(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        # R2 has no regions, but the signer requires the field to be set.
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


# ----------------------------------------------------------------------------------
# Operations
# ----------------------------------------------------------------------------------

def put_file(local: Path, key: str) -> int:
    """Upload a file. Returns the number of bytes sent."""
    local = Path(local)
    if not local.exists():
        raise ObjectStoreError(f"nothing to upload: {local} does not exist")
    size = local.stat().st_size
    client().upload_file(str(local), bucket(), key)
    logger.info("uploaded %s -> s3://%s/%s (%.1f MB)", local.name, bucket(), key, size / 1e6)
    return size


def get_file(key: str, local: Path) -> int:
    """Download an object to `local`, creating parent directories. Returns bytes received.

    Writes to a temporary name and renames, so an interrupted download can never leave a
    half-written warehouse in place of a good one.
    """
    local = Path(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    tmp = local.with_suffix(local.suffix + ".part")
    client().download_file(bucket(), key, str(tmp))
    tmp.replace(local)
    size = local.stat().st_size
    logger.info("downloaded s3://%s/%s -> %s (%.1f MB)", bucket(), key, local.name, size / 1e6)
    return size


def exists(key: str) -> bool:
    from botocore.exceptions import ClientError
    try:
        client().head_object(Bucket=bucket(), Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def list_keys(prefix: str = "") -> Iterator[str]:
    """Every key under `prefix`, following pagination.

    A plain `list_objects_v2` stops at 1000 keys and gives no sign that it did — which, with one
    Bronze snapshot per source per day, is reached in under a year.
    """
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def delete(key: str) -> None:
    client().delete_object(Bucket=bucket(), Key=key)


def bronze_key(source: str, filename: str) -> str:
    """Where a Bronze snapshot lives in the bucket.

    Mirrors the local layout (`data/bronze/<source>/<date>.jsonl.gz`) so that a bucket listing
    and a directory listing can be compared by eye.
    """
    return f"{BRONZE_PREFIX}/{source}/{filename}"


def check_writable() -> None:
    """Prove the credentials can write, not merely read.

    An R2 API token defaults to read-only, and a read-only token lists a bucket perfectly well —
    so a "connection OK" check passes and the first real upload fails. That is a bad place to
    find out, especially inside a scheduled job. This writes a marker, reads it back, and
    deletes it.
    """
    key = "_healthcheck/writable"
    payload = b"pipeline write check"
    c = client()
    try:
        c.put_object(Bucket=bucket(), Key=key, Body=payload)
    except Exception as exc:
        raise ObjectStoreError(
            f"cannot write to s3://{bucket()}/ — {type(exc).__name__}: {exc}. "
            f"An R2 API token needs 'Object Read & Write'; read-only tokens can still list."
        ) from exc
    back = c.get_object(Bucket=bucket(), Key=key)["Body"].read()
    c.delete_object(Bucket=bucket(), Key=key)
    if back != payload:
        raise ObjectStoreError("wrote to the bucket but read back different bytes")
