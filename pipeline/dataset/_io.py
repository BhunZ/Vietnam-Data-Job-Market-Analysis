"""Artifact I/O + provenance for the dataset layer.

Every artifact written through here is appended to a single MANIFEST.jsonl with its
sha256, row count, schema version, producer, and timestamp — so any later file can be
audited and the build reproduced. Artifacts are immutable: a new version is a new path,
never an overwrite.

Formats (best practice): Parquet for tabular/columnar (embeddings, clusters, features,
splits), JSONL for nested LLM outputs, YAML for taxonomy/config, Markdown for reports.
CSV is intentionally avoided for text/nested fields (cp1252 unicode pain on Windows).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..utils.config import DATA_DIR, REPO_ROOT

# ---- directory layout -------------------------------------------------------
DATASET_DIR = DATA_DIR / "dataset"
TEXT_DIR = DATASET_DIR / "text"                 # LOCAL-ONLY full JD/title (not released)
DISCOVERY_DIR = DATASET_DIR / "discovery"       # embeddings, clusters, report
ANNOTATION_DIR = DATASET_DIR / "annotation"     # deferred (judge votes, agreement, review)
MANIFEST_PATH = DATASET_DIR / "manifests" / "MANIFEST.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "nogit"
    except Exception:  # noqa: BLE001
        return "nogit"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(*parts: str) -> str:
    """Stable hash of a record's content (for dedup / provenance keying)."""
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def manifest_append(path: Path, *, rows: int, schema_version: str,
                    produced_by: str, config_run_id: str | None = None) -> None:
    """Record one artifact in the append-only MANIFEST.jsonl with its sha256."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    rel = path.relative_to(REPO_ROOT) if REPO_ROOT in path.parents else path
    entry = {
        "artifact_path": str(rel).replace("\\", "/"),
        "sha256": sha256_file(path),
        "rows": rows,
        "schema_version": schema_version,
        "produced_by": f"{produced_by}@{_git_sha()}",
        "config_run_id": config_run_id,
        "created_at": _now(),
    }
    with MANIFEST_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_parquet(df: pd.DataFrame, path: Path, *, schema_version: str,
                  produced_by: str, config_run_id: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")   # atomic: a crash mid-write can't corrupt the
    df.to_parquet(tmp, index=False)                # existing artifact (old file stays until replace)
    os.replace(tmp, path)
    manifest_append(path, rows=len(df), schema_version=schema_version,
                    produced_by=produced_by, config_run_id=config_run_id)
    return path


def write_text(text: str, path: Path, *, schema_version: str, produced_by: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    manifest_append(path, rows=text.count("\n") + 1, schema_version=schema_version,
                    produced_by=produced_by)
    return path
