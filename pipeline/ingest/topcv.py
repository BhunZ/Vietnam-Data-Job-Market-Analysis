"""TopCV connector.

TopCV WAF-blocks anonymous requests (HTTP 403), so listings are fetched through
ScraperAPI with JS render enabled (config: use_scraperapi + scraperapi_render). The
search page renders job cards server-side once the WAF is bypassed.

Selectors are kept defensive (multiple fallbacks) because TopCV markup changes; they are
validated/tuned against a rendered sample. Salary text is never parsed.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.topcv")

_WS = re.compile(r"\s+")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return _WS.sub(" ", text).strip() or None


class TopCVConnector(BaseConnector):
    source = "topcv"

    def _page_size(self) -> int:
        return int(self.client.cfg.get("cards_per_page", 25))

    def _listing_url(self, category: str, page: int) -> str:
        base = self.client.cfg["base_url"]
        path = self.client.cfg.get("listing_path", "/tim-viec-lam-{category}").format(
            category=category)
        url = f"{base}{path}"
        if page > 1:
            url += f"?page={page}"
        return url

    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        url = self._listing_url(category, page)
        res = self.client.fetch(url, f"listing_{category}_p{page}.html")
        soup = BeautifulSoup(res.text, "lxml")
        cards = (soup.select("div.job-item-search-result")
                 or soup.select("div.job-item-2")
                 or soup.select("div[data-job-id]")
                 or soup.select(".job-list-search-result .job-item"))
        return [self._parse_card(c, category) for c in cards if self._job_id(c)]

    @staticmethod
    def _job_id(card) -> str | None:
        return (card.get("data-job-id") or card.get("data-job")
                or (card.select_one("a[data-job-id]") or {}).get("data-job-id")
                if hasattr(card, "get") else None)

    def _parse_card(self, card, category: str) -> BronzeJob:
        title_a = card.select_one("h3 a, .title a, a.job-item-title, h3.title a")
        title = _clean(title_a.get_text() if title_a else None)
        url = title_a.get("href") if title_a else None
        company_a = card.select_one(".company-name, .company a, a.company")
        company = _clean(company_a.get_text() if company_a else None)
        loc_el = card.select_one(".address, .city, .location, .job-location")
        location = _clean(loc_el.get_text() if loc_el else None)
        skills = [_clean(s.get_text()) for s in card.select(".tag, .skill, .label-content a")
                  if _clean(s.get_text())]
        date_el = card.select_one(".time, .deadline, .job-deadline, .label-update")
        posted = _clean(date_el.get_text() if date_el else None)
        return BronzeJob(
            source=self.source,
            source_job_id=str(self._job_id(card)),
            title_raw=title,
            company_raw=company,
            location_raw=location,
            description_raw=None,  # detail page fetch added once listing is validated
            skills_raw=skills,
            posted_date_raw=posted,
            url=url,
            ingested_at=datetime.now(timezone.utc),
            extra={"category_seen_in": category, "salary_status": "ignored_out_of_scope"},
        )

    def estimate_volume(self) -> dict:
        try:
            rows = self.fetch_listing(self.client.cfg.get("categories", ["data"])[0], 1)
            return {"page1_cards": len(rows)}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
