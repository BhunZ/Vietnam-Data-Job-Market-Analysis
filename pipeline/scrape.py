"""Scaled multi-source scrape + capacity/block report.

Sweeps every *enabled* source at volume (full pagination + dedup), persists raw to
data/raw/ and a Bronze JSONL per source to data/bronze/, and prints a consolidated
report: per-site method, block status, pages fetched, distinct postings, JD coverage,
errors, and ScraperAPI credits consumed.

Run:  python -m pipeline scrape [--jd-limit 25]
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from .ingest import CONNECTORS
from .models import BronzeJob
from .utils.config import DATA_DIR, get_secrets, load_sources_config
from .utils.http import ScrapeClient

log = logging.getLogger("pipeline.scrape")


def _credits_left() -> int | None:
    """Query ScraperAPI account for remaining credits (best effort)."""
    keys = get_secrets().keys
    if not keys:
        return None
    try:
        r = requests.get("https://api.scraperapi.com/account",
                         params={"api_key": keys[0]}, timeout=30)
        if r.status_code == 200:
            d = r.json()
            return int(d.get("requestLimit", 0)) - int(d.get("requestCount", 0))
    except Exception:  # noqa: BLE001
        return None
    return None


def _persist(rows: list[BronzeJob], source: str) -> Path:
    # Flat, overwritten each run — the current snapshot. History lives in the DuckDB
    # warehouse (run `python -m pipeline load` after scraping), not in dated folders.
    out = DATA_DIR / "bronze" / source
    out.mkdir(parents=True, exist_ok=True)
    path = out / "latest.jsonl"

    # Carry-forward guard: a listing-only re-scrape must NOT wipe JD/skills that `enrich`
    # (or a prior detail fetch) already added. Restore description_raw / skills_raw from the
    # previous latest.jsonl for the same source_job_id when this run's value is empty.
    prev: dict[str, dict] = {}
    if path.exists():
        for line in path.open(encoding="utf-8"):
            try:
                d = json.loads(line)
                prev[str(d.get("source_job_id"))] = d
            except Exception:  # noqa: BLE001
                pass
    if prev:
        for r in rows:
            old = prev.get(str(r.source_job_id))
            if not old:
                continue
            if not r.description_raw and old.get("description_raw"):
                r.description_raw = old["description_raw"]
            if not r.skills_raw and old.get("skills_raw"):
                r.skills_raw = old["skills_raw"]

    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(r.model_dump_json() + "\n")
    return path


def _enabled_sources() -> list[str]:
    cfg = load_sources_config().get("sources", {})
    return [s for s, c in cfg.items() if c.get("enabled")]


def run_scrape(jd_limit: int = 25, max_live_fetches: int = 40,
               run_date: str | None = None) -> None:
    run_date = run_date or date.today().isoformat()  # label for this run's snapshot
    sources = _enabled_sources()
    cfg_all = load_sources_config().get("sources", {})

    print(f"\n{'='*74}\nSCALED MULTI-SOURCE SCRAPE — run_date={run_date}\n{'='*74}")
    print(f"Enabled sources: {sources}")
    disabled = [s for s in cfg_all if s not in sources]
    if disabled:
        print(f"Disabled       : {disabled}  (see config/sources.yml for why)")
    print(f"Live ScraperAPI fetch cap (credit guard): {max_live_fetches} per source")

    # Per-key credit report up front.
    for k in get_secrets().keys:
        print(f"  key {k[:6]}… credits left: {ScrapeClient.key_credits_left(k)}")
    credits_before = _credits_left()
    print(f"ScraperAPI credits before (primary): {credits_before}")

    results = {}
    for src in sources:
        print(f"\n{'-'*74}\n>>> {src.upper()}\n{'-'*74}")
        conn = CONNECTORS[src](run_date=run_date)
        conn.client.max_live_fetches = max_live_fetches
        method = "ScraperAPI" if conn.client.cfg.get("use_scraperapi") else "direct"
        jd = jd_limit if src == "itviec" else 0  # only ITviec needs per-job JD fetch
        try:
            rows, stats = conn.scrape_all(jd_limit=jd)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}")
            results[src] = {"status": "FAILED", "error": str(exc)}
            continue
        path = _persist(rows, src)
        # JD coverage: rows with a non-empty description.
        with_desc = sum(1 for r in rows if r.description_raw)
        cities = Counter(c for r in rows for c in [r.extra.get("city")] if c) \
            if src == "itviec" else Counter(c for r in rows for c in (r.extra.get("cities") or []))
        results[src] = {
            "status": "OK", "method": method, "distinct": len(rows),
            "pages": stats["pages_fetched"], "errors": stats["errors"],
            "jd_fetched": stats["jd_fetched"], "with_desc": with_desc,
            "per_item": stats["per_item"], "bronze": str(path),
            "top_cities": cities.most_common(5),
        }
        print(f"  method        : {method}")
        print(f"  pages fetched : {stats['pages_fetched']}   errors: {stats['errors']}")
        print(f"  distinct jobs : {len(rows)}")
        print(f"  JD coverage   : {with_desc}/{len(rows)} have description"
              f" ({'inline' if src != 'itviec' else f'{stats['jd_fetched']} fetched'})")
        print(f"  per query/cat : {stats['per_item']}")
        print(f"  top cities    : {cities.most_common(5)}")
        print(f"  bronze written: {path}")

    credits_after = _credits_left()
    print(f"\n{'='*74}\nSUMMARY\n{'='*74}")
    print(f"{'source':14s} {'status':7s} {'method':11s} {'distinct':>8s} {'pages':>6s} {'errors':>7s} {'JD':>10s}")
    for src in sources:
        r = results.get(src, {})
        if r.get("status") == "OK":
            jd = f"{r['with_desc']}/{r['distinct']}"
            print(f"{src:14s} {'OK':7s} {r['method']:11s} {r['distinct']:>8d} {r['pages']:>6d} {r['errors']:>7d} {jd:>10s}")
        else:
            print(f"{src:14s} {'FAIL':7s} {r.get('error','')[:60]}")
    total = sum(r["distinct"] for r in results.values() if r.get("status") == "OK")
    print(f"\nTOTAL distinct postings scraped (pre cross-source dedup): {total}")
    if credits_before is not None and credits_after is not None:
        print(f"ScraperAPI credits used this run: {credits_before - credits_after} "
              f"(remaining: {credits_after})")
    print(f"\nNOTE: TopDev is disabled by default — its job API is robots.txt-disallowed.")
    print("Done.\n")
