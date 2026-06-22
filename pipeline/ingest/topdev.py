"""TopDev connector.

COMPLIANCE NOTE — read before enabling:
TopDev's structured jobs come from ``https://api.topdev.vn/td/v2/jobs`` (rich JSON,
JD included). BUT ``api.topdev.vn/robots.txt`` is ``User-agent: * / Disallow: /``
(only Google bots allowed). The main site ``topdev.vn`` allows ``/viec-lam-it`` in
robots, but its HTML renders only ~15 promoted jobs server-side; the real search
results are loaded client-side from the disallowed API.

Therefore scraping TopDev is NOT robots-compliant by default. This connector targets
the API but refuses to run unless the operator explicitly acknowledges overriding
robots for personal/educational use by setting ``robots_override_ack: true`` AND
``respect_robots: false`` for this source in config/sources.yml.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.topdev")

_WS = re.compile(r"\s+")
# Dates come as nested objects {date:'DD-MM-YYYY', datetime, since}: published/created/refreshed.
_FIELDS = ("id,title,slug,detail_url,published,created,refreshed,content,requirements,"
           "company,addresses,skills_arr,skills_str,job_levels,salary,is_salary_visible")


def _clean(t):
    return _WS.sub(" ", t).strip() if t else None


def _html_to_text(html):
    if not html:
        return None
    if isinstance(html, list):  # TopDev requirements/content can be a list of strings
        html = " ".join(str(x) for x in html)
    elif not isinstance(html, str):
        html = str(html)
    return _clean(BeautifulSoup(html, "lxml").get_text(" "))


class TopDevConnector(BaseConnector):
    source = "topdev"

    def _ensure_allowed(self) -> None:
        if not self.client.cfg.get("robots_override_ack"):
            raise PermissionError(
                "TopDev's job API (api.topdev.vn) is robots.txt-disallowed and its HTML "
                "carries no search data. Scraping it is not robots-compliant. To proceed "
                "for personal/educational use, set robots_override_ack: true and "
                "respect_robots: false for topdev in config/sources.yml."
            )

    def _page_size(self) -> int:
        return 10  # TopDev API fixes per_page=10 regardless of any limit param

    def _api_url(self) -> str:
        return self.client.cfg.get("jobs_api", "https://api.topdev.vn/td/v2/jobs")

    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        self._ensure_allowed()
        hits, _total = self._query(category, page)
        return [self._parse_job(j, category) for j in hits]

    def _query(self, keyword: str, page: int) -> tuple[list[dict], int]:
        from urllib.parse import urlencode
        qs = urlencode({
            "page": page, "keyword": keyword, "fields[job]": _FIELDS,
            "fields[company]": "id,display_name,slug", "include": "company",
        })
        url = f"{self._api_url()}?{qs}"
        safe = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
        res = self.client.fetch(url, f"jobs_{safe}_p{page}.json")
        d = json.loads(res.text)
        return d.get("data", []), int(d.get("meta", {}).get("total", 0))

    def total_for(self, keyword: str) -> int:
        return self._query(keyword, 1)[1]

    @staticmethod
    def _date(field) -> str | None:
        # TopDev date fields are objects {date:'DD-MM-YYYY', datetime, since} (or None).
        return field.get("date") if isinstance(field, dict) else None

    def _parse_job(self, j: dict, keyword: str) -> BronzeJob:
        addr = j.get("addresses") or {}
        regions = addr.get("address_region_array") or []
        desc = " \n".join(p for p in (_html_to_text(j.get("content")),
                                       _html_to_text(j.get("requirements"))) if p) or None
        company = (j.get("company") or {}).get("display_name")
        # Prefer published date; fall back to created, then refreshed.
        posted = (self._date(j.get("published")) or self._date(j.get("created"))
                  or self._date(j.get("refreshed")))
        return BronzeJob(
            source=self.source,
            source_job_id=str(j.get("id")),
            title_raw=_clean(j.get("title")),
            company_raw=_clean(company),
            location_raw=", ".join(regions) or None,
            description_raw=desc,
            skills_raw=[s for s in (j.get("skills_arr") or []) if s],
            posted_date_raw=posted,
            url=_clean(j.get("detail_url")),
            ingested_at=datetime.now(timezone.utc),
            extra={
                "query_seen_in": keyword,
                "slug": j.get("slug"),
                "regions": regions,
                "seniority_label": j.get("job_levels"),
                "salary_status": "ignored_out_of_scope",
            },
        )

    def estimate_volume(self) -> dict:
        self._ensure_allowed()
        per_q = {}
        for q in self.client.cfg.get("queries", ["data"]):
            try:
                per_q[q] = self.total_for(q)
            except Exception as exc:  # noqa: BLE001
                per_q[q] = f"ERROR {exc}"
        return {"per_query_total": per_q}
