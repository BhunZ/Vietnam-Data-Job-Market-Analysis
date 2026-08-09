"""Vieclam24h connector.

Vieclam24h is a Next.js app, so the listing HTML looks empty at first glance — the job
cards are built by client-side JavaScript. The data is still there: the server ships the
whole page state in the ``__NEXT_DATA__`` script tag, and the postings sit at::

    props.initialState.api.getJobList.data.items

Twenty per page, paginated with ``?page=N``. So no browser and no rendering service is
needed — a plain GET and a JSON parse is enough. (`?page=` is fine under their robots.txt,
which only disallows ``/*?q``; the ``/tim-kiem-viec-lam-nhanh?q=`` search route that the
category pages redirect to is the one to avoid, hence the path-shaped URLs below.)

Each record is unusually complete for this project: the requirement text is inline, so no
per-job detail fetch is needed and no ScraperAPI credit is spent. `__NEXT_DATA__` also
carries lookup tables — 65 provinces, 70 job fields — so province ids resolve to real
names instead of being guessed.

Detail URLs are reconstructed as::

    /{field-slug}/{title-slug}-c{field_id}p{province_id}id{job_id}.html

Salary (`salary_min`/`salary_max`/`salary_range`) is deliberately ignored, as everywhere
else in this pipeline.

A caveat worth knowing before trusting the volume: the site's own occupation pages are a
loose feed rather than a strict filter. Measured 2026-08-09, the `data-engineer` page was
35% Data-relevant — it opened with "Senior SMT Process Engineer" and "Civil Engineer".
Tier 0 and the labeling engine are what make that usable.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.vieclam24h")

_WS = re.compile(r"\s+")
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return _WS.sub(" ", str(text)).strip() or None


def _html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    return _clean(BeautifulSoup(html, "lxml").get_text(" "))


def _as_list(value) -> list:
    """Some id fields arrive as a list, some as a bare int (`field_ids_main` does both)."""
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _first(value):
    ids = _as_list(value)
    return ids[0] if ids else None


def _unix_to_iso(ts) -> str | None:
    """`created_at` is a unix timestamp. Return an ISO date, or None if it is unusable."""
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()


class Vieclam24hConnector(BaseConnector):
    source = "vieclam24h"

    def __init__(self, run_date: str | None = None):
        super().__init__(run_date)
        # Filled from the first page fetched; every page ships the same tables.
        self._provinces: dict[int, str] = {}
        self._fields: dict[int, str] = {}
        self._occupations: dict[int, str] = {}

    # --- URL helpers --------------------------------------------------------
    def _listing_url(self, category: str, page: int) -> str:
        base = self.client.cfg["base_url"].rstrip("/")
        group = self.client.cfg.get("occupation_group", "viec-lam-phan-tich-thong-ke-du-lieu")
        url = f"{base}/{group}/{category}.html"
        return url if page <= 1 else f"{url}?page={page}"

    def _detail_url(self, rec: dict) -> str | None:
        """Rebuild `/{occupation-slug}/{title-slug}-c{occupation}p{province}id{job}.html`.

        The `c` segment is the first `occupation_ids_main`, not `field_ids_main` — those
        differ (a Junior Data Engineer carried field 155 "other" but occupation 8
        "it-phan-mem", and the site's own link used 8).

        The site actually routes on the trailing id and ignores the rest, so a wrong slug
        still lands on the right posting. Getting it right anyway keeps the stored URL
        identical to the one a user would copy from the site.
        """
        slug = rec.get("title_slug")
        job_id = rec.get("id")
        if not slug or not job_id:
            return None
        occupation_id = _first(rec.get("occupation_ids_main"))
        province_id = _first(rec.get("province_ids"))
        occupation_slug = self._occupations.get(occupation_id) or "viec-lam"
        base = self.client.cfg["base_url"].rstrip("/")
        return f"{base}/{occupation_slug}/{slug}-c{occupation_id}p{province_id}id{job_id}.html"

    # --- lookup tables ------------------------------------------------------
    def _absorb_lookups(self, data: dict) -> None:
        if self._provinces and self._occupations:
            return
        common = (((data.get("props") or {}).get("initialState") or {})
                  .get("api", {}).get("initCommon", {}).get("data", {}))
        for p in common.get("provinces") or []:
            if p.get("id") is not None:
                self._provinces[p["id"]] = p.get("name") or p.get("original_name")
        for f in common.get("job_field") or []:
            if f.get("id") is not None:
                self._fields[f["id"]] = f.get("slug") or f.get("code")
        for o in common.get("occupation") or []:
            if o.get("id") is not None:
                self._occupations[o["id"]] = o.get("slug")
        if self._provinces:
            log.info("vieclam24h lookups: %d provinces, %d fields, %d occupations",
                     len(self._provinces), len(self._fields), len(self._occupations))

    def _locations(self, rec: dict) -> str | None:
        names = [self._provinces.get(i) for i in _as_list(rec.get("province_ids"))]
        return _clean(", ".join(n for n in names if n)) or None

    # --- parsing ------------------------------------------------------------
    def _extract_items(self, html: str) -> list[dict]:
        m = _NEXT_DATA.search(html)
        if not m:
            log.warning("vieclam24h: no __NEXT_DATA__ in response (layout changed?)")
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            log.warning("vieclam24h: __NEXT_DATA__ is not valid JSON: %s", exc)
            return []
        self._absorb_lookups(data)
        try:
            return (data["props"]["initialState"]["api"]["getJobList"]["data"]["items"]) or []
        except (KeyError, TypeError):
            log.warning("vieclam24h: getJobList missing from page state (layout changed?)")
            return []

    def _to_bronze(self, rec: dict, category: str) -> BronzeJob | None:
        job_id = rec.get("id")
        if job_id is None:
            return None

        # The requirement blocks are the closest thing to a JD and are already inline.
        jd_parts = [
            _html_to_text(rec.get("job_requirement_html")) or _clean(rec.get("job_requirement")),
            _html_to_text(rec.get("other_requirement_html")) or _clean(rec.get("other_requirement")),
        ]
        description = _clean(" ".join(p for p in jd_parts if p))

        employer = rec.get("employer_info") or {}
        return BronzeJob(
            source=self.source,
            source_job_id=str(job_id),
            title_raw=_clean(rec.get("title")),
            company_raw=_clean(employer.get("name")),
            location_raw=self._locations(rec),
            description_raw=description,
            skills_raw=[],                       # not exposed as a structured field
            posted_date_raw=_unix_to_iso(rec.get("created_at")),
            url=self._detail_url(rec),
            ingested_at=datetime.now(timezone.utc),
            extra={
                "category_seen_in": [category],
                "level_requirement": rec.get("level_requirement"),
                "degree_requirement": rec.get("degree_requirement"),
                "experience_range": rec.get("experience_range"),
                "working_method": rec.get("working_method"),
                "province_ids": rec.get("province_ids"),
                "occupation_ids_main": rec.get("occupation_ids_main"),
                "field_ids_main": rec.get("field_ids_main"),
                "vacancy_quantity": rec.get("vacancy_quantity"),
                "total_views": rec.get("total_views"),
                "updated_at": _unix_to_iso(rec.get("updated_at")),
                # Presence only — the value is never read, same rule as every other source.
                "salary_status": bool(rec.get("salary_min") or rec.get("salary_max")),
            },
        )

    # --- BaseConnector ------------------------------------------------------
    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        url = self._listing_url(category, page)
        res = self.client.fetch(url, f"listing_{category}_p{page}.html", volatile=True)
        out = []
        for rec in self._extract_items(res.text):
            job = self._to_bronze(rec, category)
            if job:
                out.append(job)
        return out

    def estimate_volume(self) -> dict:
        """Headline count per occupation page, from the page title."""
        per = {}
        for cat in self._scrape_items():
            try:
                res = self.client.fetch(self._listing_url(cat, 1),
                                        f"listing_{cat}_p1.html", volatile=True)
                m = re.search(r"Tuyển dụng\s+(\d[\d.,]*)\s+việc làm", res.text)
                per[cat] = int(m.group(1).replace(".", "").replace(",", "")) if m else None
            except Exception as exc:  # noqa: BLE001
                log.warning("vieclam24h volume probe failed for %s: %s", cat, exc)
                per[cat] = None
        return {"source": self.source, "per_category": per}
