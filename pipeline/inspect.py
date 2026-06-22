"""Phase 1 spike: pull a small ITviec sample, persist raw, and print the data shape
(fields, types, example values, null rates, how skills/role/location are represented)
plus a volume estimate of available VN Data postings.

Run:  python -m pipeline inspect --source itviec --sample 25 --details 10
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from .ingest import CONNECTORS
from .models import BronzeJob
from .utils.config import DATA_DIR

log = logging.getLogger("pipeline.inspect")

# Categories used to build the sample (page 1 then 2 of data-engineer is plenty for ~25).
_SAMPLE_CATEGORY = "data-engineer"


def _collect_sample(connector, sample_size: int) -> list[BronzeJob]:
    rows: dict[str, BronzeJob] = {}
    page = 1
    while len(rows) < sample_size and page <= 3:
        batch = connector.fetch_listing(_SAMPLE_CATEGORY, page)
        if not batch:
            break
        for job in batch:
            rows.setdefault(job.source_job_id, job)
        page += 1
    return list(rows.values())[:sample_size]


def _null_rates(rows: list[BronzeJob]) -> dict[str, str]:
    n = len(rows) or 1
    fields = ["title_raw", "company_raw", "location_raw", "description_raw",
              "skills_raw", "posted_date_raw", "url"]
    out = {}
    for f in fields:
        missing = sum(1 for r in rows if not getattr(r, f))
        out[f] = f"{missing}/{len(rows)} null ({100*missing/n:.0f}%)"
    return out


def _persist_bronze(rows: list[BronzeJob], source: str, run_date: str) -> Path:
    out_dir = DATA_DIR / "bronze" / source
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sample.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(r.model_dump_json() + "\n")
    return path


def run_inspect(source: str = "itviec", sample_size: int = 25, details: int = 10) -> None:
    run_date = date.today().isoformat()
    connector = CONNECTORS[source](run_date=run_date)

    print(f"\n{'='*72}\nPHASE 1 INSPECTION — source={source}  run_date={run_date}\n{'='*72}")

    # 1) Volume estimate ----------------------------------------------------
    print("\n[1/3] Estimating available Data-posting volume (sweeping category page 1)...")
    vol = connector.estimate_volume()

    # 2) Sample -------------------------------------------------------------
    print(f"\n[2/3] Pulling a sample of ~{sample_size} '{_SAMPLE_CATEGORY}' postings...")
    rows = _collect_sample(connector, sample_size)
    print(f"      collected {len(rows)} unique postings from listing pages.")

    # 3) Detail (description_raw) ------------------------------------------
    if details > 0:
        print(f"\n[3/3] Fetching job descriptions for the first {min(details, len(rows))} postings...")
        for job in rows[:details]:
            connector.fetch_detail(job)

    bronze_path = _persist_bronze(rows, source, run_date)

    # ---- Report -----------------------------------------------------------
    print(f"\n{'-'*72}\nA. AVAILABLE FIELDS & TYPES (Bronze schema)\n{'-'*72}")
    for name, field in BronzeJob.model_fields.items():
        print(f"  {name:18s} : {field.annotation}")

    print(f"\n{'-'*72}\nB. NULL RATES across {len(rows)} sampled postings\n{'-'*72}")
    for f, rate in _null_rates(rows).items():
        print(f"  {f:18s} : {rate}")

    print(f"\n{'-'*72}\nC. EXAMPLE VALUES (first posting)\n{'-'*72}")
    if rows:
        ex = rows[0]
        print(f"  source_job_id   : {ex.source_job_id}")
        print(f"  title_raw       : {ex.title_raw}")
        print(f"  company_raw     : {ex.company_raw}")
        print(f"  location_raw    : {ex.location_raw}")
        print(f"  posted_date_raw : {ex.posted_date_raw}")
        print(f"  skills_raw      : {ex.skills_raw}")
        print(f"  url             : {ex.url}")
        d = ex.description_raw
        print(f"  description_raw : {(d[:240] + '...') if d else None}")
        print(f"  extra           : {json.dumps(ex.extra, ensure_ascii=False)}")

    print(f"\n{'-'*72}\nD. HOW SKILLS / ROLE / LOCATION ARE REPRESENTED\n{'-'*72}")
    skill_counter = Counter(s for r in rows for s in r.skills_raw)
    print(f"  SKILLS  : structured tag anchors per card (mapped 1:1 to /it-jobs/<skill>).")
    print(f"            {len(skill_counter)} distinct tags across sample. Top 15:")
    for s, c in skill_counter.most_common(15):
        print(f"              {c:3d}  {s}")
    pos_counter = Counter(r.extra.get("position_label") for r in rows)
    print(f"\n  ROLE    : NOT a discrete field. Inferred from title + a 'position label' tag.")
    print(f"            position-label tag values seen: {dict(pos_counter)}")
    wm_counter = Counter(r.extra.get("work_model") for r in rows)
    city_counter = Counter(r.extra.get("city") for r in rows)
    print(f"\n  LOCATION: 'work_model + city' on the card (e.g. 'At office Ha Noi').")
    print(f"            work_model: {dict(wm_counter)}")
    print(f"            city      : {dict(city_counter)}")

    print(f"\n{'-'*72}\nE. VOLUME ESTIMATE — available VN Data postings on ITviec\n{'-'*72}")
    print("  Per-category site-reported totals (categories OVERLAP — a posting can carry")
    print("  several tags, so these do NOT sum to a distinct count):")
    for cat, info in vol["per_category"].items():
        tot = info.get("site_total")
        print(f"    {cat:24s} : {str(tot):>5s} jobs   (page-1 cards: {info.get('keys_on_p1')})")
    print(f"\n  Sum of category totals (UPPER bound, double-counts): {vol['sum_site_totals']}")
    print(f"  Distinct job UUIDs observed on page-1 of all cats   : {vol['distinct_keys_on_page1']}"
          f"  (of {vol['collected_keys_on_page1']} collected -> "
          f"{100*(1-vol['distinct_keys_on_page1']/max(vol['collected_keys_on_page1'],1)):.0f}% overlap)")

    print(f"\n{'-'*72}\nF. PERSISTED ARTIFACTS\n{'-'*72}")
    print(f"  raw HTML cache : {DATA_DIR / 'raw' / source}")
    print(f"  bronze sample  : {bronze_path}")
    print(f"\nDone. Review the above, then we design the Silver schema together.\n")
