"""Quality gates: refuse to spend money on data that looks wrong.

The failure this exists to catch is a job board changing its HTML. A parser that breaks
loudly returns zero postings and is obvious. A parser that breaks quietly returns several
hundred plausible-looking ids that are all new, and the pipeline then burns a night of LLM
quota labeling rubbish and files it in the warehouse next to the real thing.

So: after `load`, before `label`, compare how many postings are new against how much
corpus there was. Too many and the run stops with a non-zero exit.

The threshold scales with the gap between runs, which the 2026-08-09 run made obvious. It
came eight weeks after the previous one and legitimately brought 1490 new postings against
a 1701 corpus — 88%. A flat 25% would have called that a parser break. Postings expire off
these boards in about a month, so churn accumulates with the gap and the allowance has to
as well.
"""

from __future__ import annotations

import logging
from datetime import date

import duckdb

from .utils.config import DATA_DIR

log = logging.getLogger("pipeline.gates")

DB_PATH = DATA_DIR / "warehouse.duckdb"

#: Share of the existing corpus that may be new after a 7-day gap.
BASE_NEW_PCT = 0.25
BASELINE_GAP_DAYS = 7
#: Never allow more than this, however long the gap. Everything new means nothing matched,
#: which is the signature of an id scheme changing under us.
MAX_NEW_PCT = 0.95
#: A source not seen for this long is stale: still flagged active, but nobody has looked.
STALE_SOURCE_DAYS = 21

#: Requests a full run needs, measured across the runs so far. Listing pages are re-fetched
#: every run because their cache key carries the run date; detail pages are cached forever, so
#: only genuinely new postings cost anything. A steady week lands well under this; the margin is
#: for a week where a board publishes unusually heavily.
EXPECTED_SCRAPE_REQUESTS = 400


class QualityGateFailed(RuntimeError):
    """Raised when a gate refuses to let the run continue."""


def check_scrape_quota(expected: int = EXPECTED_SCRAPE_REQUESTS) -> dict:
    """Refuse to start a scrape that cannot finish.

    ScraperAPI does not fail loudly when a key runs out — requests simply stop coming back, and
    the run ends with a partial crawl that looks exactly like a quiet week. The ingest-delta
    gate downstream would then see *fewer* postings than usual and wave it through, because it
    is built to catch a flood of bad ids, not a drought of good ones. Every posting missed that
    week is also a posting the boards may have taken down by the next run, so the loss is
    permanent.

    Checking first turns a silent, unrecoverable gap into a red run before anything is spent.
    Returns a report; raises only when the remaining budget cannot cover one run.
    """
    from .utils.config import get_secrets

    keys = get_secrets().keys
    if not keys:
        return {"checked": False, "reason": "no ScraperAPI key configured"}

    import requests

    remaining = 0
    accounts = []
    for key in keys:
        try:
            r = requests.get("https://api.scraperapi.com/account",
                             params={"api_key": key}, timeout=30)
            d = r.json()
            used, limit = int(d.get("requestCount", 0)), int(d.get("requestLimit", 0))
        except Exception as exc:  # a check that cannot run must not stop the pipeline
            accounts.append({"used": None, "limit": None, "error": type(exc).__name__})
            continue
        remaining += max(limit - used, 0)
        accounts.append({"used": used, "limit": limit})

    if all(a.get("error") for a in accounts):
        return {"checked": False, "reason": "could not reach ScraperAPI", "accounts": accounts}

    report = {"checked": True, "remaining": remaining, "expected": expected,
              "accounts": accounts}
    if remaining < expected:
        raise QualityGateFailed(
            f"ScraperAPI budget is {remaining} requests, a run needs about {expected}. "
            f"A partial crawl is indistinguishable from a quiet week downstream, and the "
            f"postings missed now may be gone by the next run. Wait for the quota to reset or "
            f"add a key.")
    return report


def _previous_snapshot(con, run_date: date) -> date | None:
    row = con.execute(
        "SELECT max(snapshot_date) FROM job_observations WHERE snapshot_date < ?",
        [run_date]).fetchone()
    return row[0] if row else None


def allowed_new_pct(gap_days: int) -> float:
    """Allowance for a gap of `gap_days`, scaled off the 7-day baseline."""
    if gap_days <= 0:
        return BASE_NEW_PCT
    return min(BASE_NEW_PCT * gap_days / BASELINE_GAP_DAYS, MAX_NEW_PCT)


def check_ingest_delta(run_date: date, allow_large: bool = False) -> dict:
    """Compare this run's new postings against the corpus that preceded it.

    Returns the numbers either way; raises `QualityGateFailed` when over the allowance and
    `allow_large` is not set.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        n_new = con.execute(
            "SELECT count(*) FROM jobs WHERE first_seen_date = ?", [run_date]).fetchone()[0]
        n_before = con.execute(
            "SELECT count(*) FROM jobs WHERE first_seen_date < ?", [run_date]).fetchone()[0]
        prev = _previous_snapshot(con, run_date)
    finally:
        con.close()

    gap_days = (run_date - prev).days if prev else BASELINE_GAP_DAYS
    allowed = allowed_new_pct(gap_days)
    pct = (n_new / n_before) if n_before else 0.0

    result = {"run_date": str(run_date), "previous_snapshot": str(prev) if prev else None,
              "gap_days": gap_days, "new": n_new, "corpus_before": n_before,
              "new_pct": round(pct, 4), "allowed_pct": round(allowed, 4),
              "passed": pct <= allowed}

    if result["passed"]:
        log.info("ingest delta gate: %d new vs %d corpus = %.1f%% (allowed %.1f%% for a %d-day gap)",
                 n_new, n_before, pct * 100, allowed * 100, gap_days)
        return result

    message = (
        f"ingest delta gate FAILED: {n_new} new postings against a corpus of {n_before} "
        f"= {pct * 100:.1f}%, over the {allowed * 100:.1f}% allowed for a {gap_days}-day gap.\n"
        f"That is what a broken parser looks like: plausible ids, none of them matching "
        f"anything already known.\n"
        f"Check a listing page under data/raw/<source>/{run_date}/ before going further. "
        f"If the postings are real, re-run with --allow-large-delta."
    )
    if allow_large:
        log.warning("%s\n(overridden by --allow-large-delta)", message)
        result["overridden"] = True
        return result
    raise QualityGateFailed(message)


def stale_sources(run_date: date, max_age_days: int = STALE_SOURCE_DAYS) -> list[dict]:
    """Sources whose postings still count as active but that nobody has scraped lately.

    TopCV was the case this was written for: blocked by DataDome from 2026-06-16, its 99
    postings sat in the analysis base flagged active for eight weeks. They were not known to
    be gone — nobody was looking, which is a different thing and should not be silently
    rounded to either 'live' or 'removed'. It was retired on 2026-08-09 and those rows marked
    inactive, so the check now guards the remaining six: a board that starts failing quietly
    looks exactly the same from here.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT source, count(*) FILTER (WHERE is_active), max(last_seen_date) "
            "FROM jobs GROUP BY source HAVING count(*) FILTER (WHERE is_active) > 0"
        ).fetchall()
    finally:
        con.close()

    out = []
    for source, n_active, last_seen in rows:
        age = (run_date - last_seen).days
        if age > max_age_days:
            out.append({"source": source, "active_rows": n_active,
                        "last_seen": str(last_seen), "age_days": age})
    return sorted(out, key=lambda d: -d["age_days"])


def print_report(run_date: date, delta: dict, stale: list[dict]) -> None:
    print(f"\n{'='*64}\nQUALITY GATES  (run_date={run_date})\n{'='*64}")
    print(f"ingest delta : {delta['new']} new vs {delta['corpus_before']} corpus "
          f"= {delta['new_pct']*100:.1f}%  (allowed {delta['allowed_pct']*100:.1f}% "
          f"for a {delta['gap_days']}-day gap)  -> {'PASS' if delta['passed'] else 'FAIL'}")
    if not stale:
        print("stale sources: none")
        return
    print(f"stale sources: {len(stale)} (active rows nobody has re-observed)")
    for s in stale:
        print(f"  {s['source']:14s} {s['active_rows']:5d} active, last seen "
              f"{s['last_seen']} ({s['age_days']} days ago)")
