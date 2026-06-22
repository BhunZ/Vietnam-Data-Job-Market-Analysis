"""VietnamWorks connector.

VietnamWorks exposes a public JSON search API used by its own front-end:
``POST https://ms.vietnamworks.com/job-search/v1.0/search`` with a JSON body. The host
has no robots.txt (404 -> allowed). Each hit is fully structured and already includes
the JD (``jobDescription`` + ``jobRequirement``), structured ``skills``, working
locations, an ABSOLUTE ``createdOn`` date, seniority (``jobLevelVI``) and language
(``languageSelectedVI``) — so NO per-job detail fetch is needed.

Salary fields (``salary``/``salaryMin``/``salaryMax``/``prettySalary``) are intentionally
ignored — never parsed or stored.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.vietnamworks")

_WS = re.compile(r"\s+")

_RETRIEVE_FIELDS = [
    "jobId", "jobTitle", "jobUrl", "alias", "companyName", "companyId",
    "jobDescription", "jobRequirement", "skills", "workingLocations", "address",
    "jobLevel", "jobLevelVI", "languageSelectedVI", "typeWorkingVI",
    "industriesV3", "jobFunctionsV3", "createdOn", "approvedOn", "expiredOn",
    "yearsOfExperience", "isSalaryVisible",  # salary flag only; value never read
]


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return _WS.sub(" ", text).strip() or None


def _html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    return _clean(BeautifulSoup(html, "lxml").get_text(" "))


class VietnamWorksConnector(BaseConnector):
    source = "vietnamworks"

    def _start_page(self) -> int:
        return 0  # VietnamWorks search pages are 0-based

    def _api_url(self) -> str:
        return self.client.cfg.get(
            "search_api", "https://ms.vietnamworks.com/job-search/v1.0/search"
        )

    # --- listing ------------------------------------------------------------
    def fetch_listing(self, category: str, page: int = 0) -> list[BronzeJob]:
        """``category`` is the search query string; ``page`` is 0-based."""
        soup_hits, _total = self._search(category, page)
        return [self._parse_hit(h, category) for h in soup_hits]

    def _search(self, query: str, page: int) -> tuple[list[dict], int]:
        hits_per_page = int(self.client.cfg.get("hits_per_page", 100))
        body = {
            "userId": 0, "query": query, "filter": [], "ranges": [], "order": [],
            "hitsPerPage": hits_per_page, "page": page, "retrieveFields": _RETRIEVE_FIELDS,
        }
        safe_q = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        cache_name = f"search_{safe_q}_p{page}.json"
        res = self.client.fetch(self._api_url(), cache_name, method="POST", json_body=body)
        data = json.loads(res.text)
        return data.get("data", []), int(data.get("meta", {}).get("nbHits", 0))

    def total_for(self, query: str) -> int:
        return self._search(query, 0)[1]

    # --- parse --------------------------------------------------------------
    def _parse_hit(self, h: dict, query: str) -> BronzeJob:
        skills = [s.get("skillName") for s in (h.get("skills") or []) if s.get("skillName")]
        locs = h.get("workingLocations") or []
        cities = [l.get("cityNameVI") or l.get("cityName") for l in locs]
        cities = [c for c in cities if c]
        desc = _html_to_text(h.get("jobDescription"))
        req = _html_to_text(h.get("jobRequirement"))
        description = " \n".join(p for p in (desc, req) if p) or None

        return BronzeJob(
            source=self.source,
            source_job_id=str(h.get("jobId")),
            title_raw=_clean(h.get("jobTitle")),
            company_raw=_clean(h.get("companyName")),
            location_raw=", ".join(cities) or _clean(h.get("address")),
            description_raw=description,
            skills_raw=skills,
            posted_date_raw=h.get("createdOn"),  # absolute ISO datetime
            url=_clean(h.get("jobUrl")) or (f"https://www.vietnamworks.com/{h.get('alias')}-jv"
                                            if h.get("alias") else None),
            ingested_at=datetime.now(timezone.utc),
            extra={
                "query_seen_in": query,
                "cities": cities,
                "seniority_label": h.get("jobLevelVI") or h.get("jobLevel"),
                "language_req_raw": h.get("languageSelectedVI"),
                "work_model_raw": h.get("typeWorkingVI"),
                "years_of_experience": h.get("yearsOfExperience"),
                "job_functions": [f.get("nameVI") or f.get("name")
                                  for f in (h.get("jobFunctionsV3") or []) if isinstance(f, dict)],
                "salary_status": "ignored_out_of_scope",
            },
        )

    # --- volume -------------------------------------------------------------
    def estimate_volume(self) -> dict:
        per_q = {}
        for q in self.client.cfg.get("queries", ["data"]):
            try:
                per_q[q] = self.total_for(q)
            except Exception as exc:  # noqa: BLE001
                per_q[q] = f"ERROR {exc}"
        return {"per_query_nbHits": per_q}
