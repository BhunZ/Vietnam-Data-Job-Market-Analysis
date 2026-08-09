"""Bronze layout: one immutable, dated snapshot per run.

Bronze used to be a single `latest.jsonl` per source, rewritten in place on every
scrape. That has two failure modes. A scrape that dies halfway takes the previous
run's raw data with it, and the warehouse can never be rebuilt from raw alone —
only the newest run exists. Dating the file fixes both: every run leaves a file
behind, and `load` can be replayed over any of them.

Layout::

    data/bronze/<source>/2026-08-09.jsonl.gz   one run, never rewritten by a later run
    data/bronze/<source>/_latest               text file naming the newest snapshot

`_latest` is a pointer file rather than a symlink because Windows only creates
symlinks under developer mode or elevation, and this project runs on Windows.

Snapshots are gzipped. Bronze is JSONL, which compresses roughly 8x: a weekly
cadence costs ~250 MB/year written plainly and ~31 MB/year gzipped. Readers sniff
the extension, so `.jsonl` snapshots written before this change still load, as
does the legacy `latest.jsonl`.

Writes go to a temp file and are then renamed into place. A crash mid-write
leaves the previous snapshot intact instead of a half-written one.

One deliberate exception to immutability: `enrich` and `topcv_browser_merge` fill
`description_raw` / `skills_raw` on the *newest* snapshot in place. They add detail
to observations already in that snapshot rather than observing anything new, and
the responses they merge are themselves cached under `data/raw/`, so nothing is
lost. A run's snapshot is "what we knew about that run", not "the first draft of it".
"""

from __future__ import annotations

import gzip
import json
import os
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from .config import DATA_DIR

BRONZE_DIR = DATA_DIR / "bronze"

# A snapshot is named for the run date. `sample.jsonl` (written by `inspect`) and
# any other stray file in the directory must not be mistaken for one.
_SNAPSHOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl(\.gz)?$")
_POINTER = "_latest"
_LEGACY = "latest.jsonl"


def source_dir(source: str) -> Path:
    return BRONZE_DIR / source


def snapshot_path(source: str, run_date: str, compressed: bool = True) -> Path:
    """Path this run's snapshot should be written to."""
    suffix = ".jsonl.gz" if compressed else ".jsonl"
    return source_dir(source) / f"{run_date}{suffix}"


def list_snapshots(source: str) -> list[Path]:
    """Every dated snapshot for a source, oldest first.

    Names are ISO dates, so lexical order is chronological order.
    """
    d = source_dir(source)
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.is_file() and _SNAPSHOT_RE.match(p.name)),
                  key=lambda p: p.name)


def latest_path(source: str) -> Path | None:
    """Newest snapshot for a source, or None.

    Resolution order: the `_latest` pointer, then the newest dated snapshot (in
    case the pointer is missing or stale), then the pre-dating `latest.jsonl`.
    """
    d = source_dir(source)
    pointer = d / _POINTER
    if pointer.is_file():
        target = d / pointer.read_text(encoding="utf-8").strip()
        if target.is_file():
            return target

    snaps = list_snapshots(source)
    if snaps:
        return snaps[-1]

    legacy = d / _LEGACY
    return legacy if legacy.is_file() else None


def set_latest(source: str, path: Path) -> None:
    (source_dir(source) / _POINTER).write_text(path.name, encoding="utf-8")


def _open_read(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open(encoding="utf-8")


def iter_rows(path: Path) -> Iterator[dict]:
    """Yield each JSON object in a snapshot. Handles gzipped and plain files."""
    with _open_read(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_latest(source: str) -> list[dict]:
    """Rows of the newest snapshot; empty list when the source has none."""
    path = latest_path(source)
    return list(iter_rows(path)) if path else []


def write_snapshot(source: str, run_date: str, lines: Iterable[str],
                   compressed: bool = True) -> Path:
    """Write one run's snapshot and move the `_latest` pointer onto it.

    `lines` are JSON strings without trailing newlines. The write lands on a temp
    file first and is renamed in, so an interrupted run cannot leave a truncated
    snapshot behind.
    """
    path = snapshot_path(source, run_date, compressed=compressed)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    opener = (lambda: gzip.open(tmp, "wt", encoding="utf-8")) if compressed \
        else (lambda: tmp.open("w", encoding="utf-8"))
    with opener() as fh:
        for line in lines:
            fh.write(line + "\n")

    os.replace(tmp, path)
    set_latest(source, path)
    return path


def rewrite_latest(source: str, lines: Iterable[str]) -> Path:
    """Overwrite the newest snapshot in place — for `enrich` / `topcv_browser_merge`.

    Raises when the source has no snapshot: these callers enrich existing rows and
    have nothing to do without one.
    """
    path = latest_path(source)
    if path is None:
        raise FileNotFoundError(f"no bronze snapshot for {source}")

    tmp = path.with_name(path.name + ".tmp")
    opener = (lambda: gzip.open(tmp, "wt", encoding="utf-8")) if path.suffix == ".gz" \
        else (lambda: tmp.open("w", encoding="utf-8"))
    with opener() as fh:
        for line in lines:
            fh.write(line + "\n")

    os.replace(tmp, path)
    set_latest(source, path)
    return path


def available_sources() -> list[str]:
    """Sources that have at least one readable snapshot."""
    if not BRONZE_DIR.is_dir():
        return []
    return sorted(d.name for d in BRONZE_DIR.iterdir()
                  if d.is_dir() and latest_path(d.name) is not None)


def prune(source: str, keep: int) -> list[Path]:
    """Delete all but the newest `keep` snapshots. Returns what was deleted.

    Not wired into the pipeline yet — retention is a decision for whoever runs it,
    and dated Bronze is cheap enough (~31 MB/year gzipped at a weekly cadence) that
    keeping everything is a reasonable default.
    """
    snaps = list_snapshots(source)
    doomed = snaps[:-keep] if keep > 0 else []
    for p in doomed:
        p.unlink()
    return doomed
