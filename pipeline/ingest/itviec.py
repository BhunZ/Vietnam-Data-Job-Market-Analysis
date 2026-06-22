"""ITviec connector.

ITviec serves Data jobs as keyword/skill *category* pages (``/it-jobs/<slug>?page=N``),
each rendering 20 server-side ``div.job-card`` elements. Every card carries:
  * ``data-job-key``            -> stable job UUID (source_job_id),
  * a slug + ``/content`` URL   -> the internal detail endpoint (preferred over HTML),
  * title (h3), company, working-model + city, relative posted-date, and skill tags.

Salary appears only as "Sign in to view salary" and is intentionally NOT parsed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.itviec")

_WS = re.compile(r"\s+")
_WORK_MODELS = ("At office", "Hybrid", "Remote")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    out = _WS.sub(" ", text).strip()
    return out or None


class ITviecConnector(BaseConnector):
    source = "itviec"

    # --- URL helpers --------------------------------------------------------
    def _listing_url(self, category: str, page: int) -> str:
        base = self.client.cfg["base_url"]
        url = f"{base}/it-jobs/{category}"
        if page > 1:
            url += f"?{self.client.cfg.get('page_param', 'page')}={page}"
        return url

    # --- listing ------------------------------------------------------------
    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        soup, _total = self._listing_soup(category, page)
        return [self._parse_card(c, category) for c in soup.select("div.job-card")]

    def _listing_soup(self, category: str, page: int) -> tuple[BeautifulSoup, int | None]:
        url = self._listing_url(category, page)
        cache_name = f"listing_{category}_p{page}.html"
        res = self.client.fetch(url, cache_name)
        soup = BeautifulSoup(res.text, "lxml")
        return soup, self._parse_total(soup)

    @staticmethod
    def _parse_total(soup: BeautifulSoup) -> int | None:
        el = soup.select_one(".headline-total-jobs")
        if not el:
            return None
        m = re.search(r"([\d,]+)", el.get_text(" ", strip=True))
        return int(m.group(1).replace(",", "")) if m else None

    # --- card parsing -------------------------------------------------------
    def _parse_card(self, card, category: str) -> BronzeJob:
        attrs = card.attrs
        job_key = attrs.get("data-job-key")
        slug = attrs.get("data-search--job-selection-job-slug-value")
        content_path = attrs.get("data-search--job-selection-job-url-value")
        base = self.client.cfg["base_url"]

        title = _clean(card.select_one("h3").get_text() if card.select_one("h3") else None)

        # Company: name span next to the logo, fallback to the /companies/ anchor text.
        company = _clean(
            card.select_one("span.ims-2").get_text() if card.select_one("span.ims-2") else None
        )
        if not company:
            comp_a = card.select_one("a[href^='/companies/']")
            company = _clean(comp_a.get_text() if comp_a else None)

        # Posted date (relative, e.g. "Posted 2 days ago").
        posted_el = card.select_one("span.small-text.text-dark-grey")
        posted = _clean(posted_el.get_text(" ") if posted_el else None)

        # Working-model + city block (e.g. "At office Ha Noi").
        loc_el = card.select_one("div.imt-1.igap-2") or card.select_one(
            "div.imt-1.d-flex.text-dark-grey"
        )
        location = _clean(loc_el.get_text(" ") if loc_el else None)
        work_model, city = self._split_location(location)

        # Position label (the role tag, e.g. "Data Engineer").
        pos_a = card.select_one("div.imt-1 a[href^='/it-jobs/']")
        position_label = _clean(pos_a.get_text() if pos_a else None)

        # Skill tags (structured anchors). Includes the position tag; kept verbatim.
        skills = [
            _clean(a.get_text())
            for a in card.select("a.itag")
            if _clean(a.get_text())
        ]

        return BronzeJob(
            source=self.source,
            source_job_id=job_key or slug or (title or "unknown"),
            title_raw=title,
            company_raw=company,
            location_raw=location,
            description_raw=None,  # filled by fetch_detail() when requested
            skills_raw=skills,
            posted_date_raw=posted,
            url=f"{base}/it-jobs/{slug}" if slug else None,
            ingested_at=datetime.now(timezone.utc),
            extra={
                "category_seen_in": category,
                "slug": slug,
                "content_url": f"{base}{content_path}" if content_path else None,
                "position_label": position_label,
                "work_model": work_model,
                "city": city,
                "salary_status": "hidden_login_required",  # never parsed
            },
        )

    @staticmethod
    def _split_location(location: str | None) -> tuple[str | None, str | None]:
        if not location:
            return None, None
        for wm in _WORK_MODELS:
            if location.startswith(wm):
                city = _clean(location[len(wm):]) or None
                return wm, city
        return None, location

    # --- detail (description) ----------------------------------------------
    def fetch_detail(self, job: BronzeJob) -> BronzeJob:
        """Fetch the job's ``/content`` detail page and set ``description_raw``."""
        content_url = job.extra.get("content_url")
        if not content_url:
            return job
        cache_name = f"detail_{job.source_job_id}.html"
        try:
            res = self.client.fetch(content_url, cache_name)
        except Exception as exc:  # noqa: BLE001
            log.warning("detail fetch failed for %s: %s", job.source_job_id, exc)
            return job
        soup = BeautifulSoup(res.text, "lxml")
        # The content fragment holds the full JD; take the visible text, salary aside.
        desc = _clean(soup.get_text(" "))
        job.description_raw = desc
        return job

    # --- volume estimate ----------------------------------------------------
    def estimate_volume(self) -> dict:
        """Sweep page 1 of each configured category: per-category site totals + the
        distinct set of job UUIDs actually observed (to gauge cross-category overlap)."""
        per_cat: dict[str, dict] = {}
        all_keys: set[str] = set()
        for cat in self.client.cfg.get("categories", []):
            try:
                soup, total = self._listing_soup(cat, 1)
            except Exception as exc:  # noqa: BLE001
                log.warning("volume: %s failed: %s", cat, exc)
                per_cat[cat] = {"site_total": None, "keys_on_p1": 0, "error": str(exc)}
                continue
            keys = [c.attrs.get("data-job-key") for c in soup.select("div.job-card")]
            keys = [k for k in keys if k]
            all_keys.update(keys)
            per_cat[cat] = {"site_total": total, "keys_on_p1": len(keys)}
        return {
            "per_category": per_cat,
            "sum_site_totals": sum(
                v["site_total"] or 0 for v in per_cat.values()
            ),
            "distinct_keys_on_page1": len(all_keys),
            "collected_keys_on_page1": sum(v.get("keys_on_p1", 0) for v in per_cat.values()),
        }
