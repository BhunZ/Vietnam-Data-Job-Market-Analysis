"""CareerViet connector.

CareerViet (formerly CareerBuilder VN) serves keyword search pages server-side over
openresty (no Cloudflare block) — direct HTML scraping, no ScraperAPI needed. Each page
renders 50 `.job-item` cards. Skills are not on the listing card (they'd need a detail
fetch), so `skills_raw` is left empty this pass; title/company/location/url are captured.
Salary ("Cạnh tranh"/amounts) is never parsed.

URL pattern: page 1 = `/viec-lam/<kw>-k-vi.html`; page N = `/viec-lam/<kw>-trang-<N>-vi.html`.
Job id is the hex code in the detail URL (`...-name.<ID>.html`).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.careerviet")

_WS = re.compile(r"\s+")
_ID_RE = re.compile(r"\.([0-9A-Fa-f]{6,})\.html")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return _WS.sub(" ", text).strip() or None


class CareerVietConnector(BaseConnector):
    source = "careerviet"

    def _page_size(self) -> int:
        return int(self.client.cfg.get("cards_per_page", 50))

    def _listing_url(self, category: str, page: int) -> str:
        base = self.client.cfg["base_url"]
        if page <= 1:
            return f"{base}/viec-lam/{category}-k-vi.html"
        return f"{base}/viec-lam/{category}-trang-{page}-vi.html"

    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        url = self._listing_url(category, page)
        res = self.client.fetch(url, f"listing_{category}_p{page}.html")
        soup = BeautifulSoup(res.text, "lxml")
        out = []
        for card in soup.select(".job-item"):
            job = self._parse_card(card, category)
            if job:
                out.append(job)
        return out

    def _parse_card(self, card, category: str) -> BronzeJob | None:
        title_a = card.select_one(".title a, .job-title a, a[href*='/tim-viec-lam/']")
        if not title_a:
            return None
        url = title_a.get("href") or ""
        if url.startswith("/"):
            url = self.client.cfg["base_url"] + url
        m = _ID_RE.search(url)
        job_id = m.group(1) if m else url
        title = _clean(title_a.get("title") or title_a.get_text())

        comp = card.select_one(".company-name, .company a, [class*=company]")
        company = _clean(comp.get_text() if comp else None)
        loc = card.select_one("[class*=location], .address, .city")
        location = _clean(loc.get_text() if loc else None)
        date_el = card.select_one("[class*=expire], [class*=update], .time, .date")
        posted = _clean(date_el.get_text() if date_el else None)

        return BronzeJob(
            source=self.source,
            source_job_id=str(job_id),
            title_raw=title,
            company_raw=company,
            location_raw=location,
            description_raw=None,  # JD/skills need a detail-page fetch (future pass)
            skills_raw=[],
            posted_date_raw=posted,
            url=url or None,
            ingested_at=datetime.now(timezone.utc),
            extra={"category_seen_in": category, "salary_status": "ignored_out_of_scope"},
        )

    def fetch_detail(self, job: BronzeJob) -> BronzeJob:
        """Populate description_raw from the detail page's JobPosting ld+json."""
        if job.description_raw or not job.url:
            return job
        try:
            res = self.client.fetch(job.url, f"detail_{job.source_job_id}.html")
        except Exception as exc:  # noqa: BLE001
            log.warning("careerviet detail %s failed: %s", job.source_job_id, exc)
            return job
        soup = BeautifulSoup(res.text, "lxml")
        for b in soup.find_all("script", type="application/ld+json"):
            try:
                d = json.loads(b.string or "")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                desc_html = d.get("description") or ""
                job.description_raw = _clean(BeautifulSoup(desc_html, "lxml").get_text(" "))
                if not job.posted_date_raw and d.get("datePosted"):
                    job.posted_date_raw = d["datePosted"]
                sk = d.get("skills")
                if sk:
                    job.skills_raw = [s.strip() for s in str(sk).split(",") if s.strip()]
                job.extra["industry"] = d.get("industry")
                job.extra["education"] = d.get("educationRequirements")
                job.extra["employment_type"] = d.get("employmentType")
                break
        return job

    def estimate_volume(self) -> dict:
        per = {}
        for c in self.client.cfg.get("categories", ["data"]):
            try:
                per[c] = len(self.fetch_listing(c, 1))
            except Exception as exc:  # noqa: BLE001
                per[c] = f"ERROR {exc}"
        return {"per_category_page1": per}
