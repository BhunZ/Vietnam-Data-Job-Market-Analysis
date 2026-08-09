"""Ingest TopCV listings captured from a real browser into a Bronze snapshot.

TopCV is the one source this pipeline's HTTP client cannot reach. DataDome fingerprints
the TLS handshake and header order, so it answers `requests` with 403 and ScraperAPI with
500 — neither is a browser and neither can pretend to be one on the free plan. A real
Chrome with the user's own session gets HTTP 200 and 50 cards a page (verified 2026-08-09).

So the browser does the fetching and this does the loading, the same split the repo already
uses in `topcv_browser_merge.py` for JD enrichment. The browser writes a JSON file::

    {"captured_at": "2026-08-09",
     "categories": {"data-engineer": [{"job_id": "...", "title": "...", ...}, ...]}}

and this turns it into `data/bronze/topcv/<run_date>.jsonl.gz` like any other source, after
which `load`, `silver`, `label` and the rest treat TopCV no differently.

Per-record fields (all optional except `job_id` and `title`)::

    job_id · title · company · city · deadline · url · skills[]

Run:  python -m pipeline import-topcv <file.json> [--run-date YYYY-MM-DD]
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from .models import BronzeJob
from .utils import bronze

log = logging.getLogger("pipeline.topcv_browser_listing")

SOURCE = "topcv"


def _clean(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _to_bronze(rec: dict, category: str) -> BronzeJob | None:
    job_id = rec.get("job_id") or rec.get("jobId") or rec.get("id")
    title = _clean(rec.get("title"))
    if not job_id or not title:
        return None
    return BronzeJob(
        source=SOURCE,
        source_job_id=str(job_id),
        title_raw=title,
        company_raw=_clean(rec.get("company")),
        location_raw=_clean(rec.get("city") or rec.get("location")),
        description_raw=None,      # listing cards carry no JD; `enrich` fills it later
        skills_raw=[s for s in (_clean(x) for x in rec.get("skills") or []) if s],
        posted_date_raw=_clean(rec.get("deadline")),
        url=_clean(rec.get("url")),
        ingested_at=datetime.now(timezone.utc),
        extra={
            "category_seen_in": [category],
            "captured_via": "browser",   # provenance: this row did not come from scrape
            "salary_status": "ignored_out_of_scope",
        },
    )


def run_import(path: Path, run_date: str | None = None) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    categories = payload.get("categories") or {}
    run_date = run_date or payload.get("captured_at") or date.today().isoformat()

    rows: dict[str, BronzeJob] = {}
    per_category: dict[str, int] = {}
    skipped = 0
    for category, records in categories.items():
        before = len(rows)
        for rec in records:
            job = _to_bronze(rec, category)
            if job is None:
                skipped += 1
                continue
            # First category to mention a posting wins, matching BaseConnector.scrape_all.
            rows.setdefault(job.source_job_id, job)
        per_category[category] = len(rows) - before

    if not rows:
        raise ValueError(f"{path} produced no usable postings "
                         f"({skipped} records lacked a job_id or title)")

    snapshot = bronze.write_snapshot(SOURCE, run_date,
                                     (r.model_dump_json() for r in rows.values()))
    return {"run_date": run_date, "distinct": len(rows), "skipped": skipped,
            "per_category": per_category, "snapshot": str(snapshot)}


def main(path: str, run_date: str | None = None) -> int:
    report = run_import(Path(path), run_date)
    print(f"\n{'='*64}\nTOPCV BROWSER IMPORT  (run_date={report['run_date']})\n{'='*64}")
    for category, n in report["per_category"].items():
        print(f"  {category:26s} +{n}")
    print(f"\n  distinct postings : {report['distinct']}")
    if report["skipped"]:
        print(f"  skipped (no id/title): {report['skipped']}")
    print(f"  bronze written    : {report['snapshot']}")
    print("\nNext: python -m pipeline load --run-date " + report["run_date"])
    return 0
