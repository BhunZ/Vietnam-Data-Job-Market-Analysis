"""Glints (VN) connector.

Glints' web app is a Next.js/Apollo SPA. The explore *page* (`/opportunities/jobs/
explore?*`) is robots.txt-disallowed, but the GraphQL API it calls
(`https://glints.com/api/v2/graphql`) is NOT disallowed and is reachable anonymously
(no login). We query `searchJobs` directly with `page`/`pageSize` pagination.

Each Job carries: title, work arrangement, absolute `createdAt`, structured `skills`,
a clean `hierarchicalJobCategory` (e.g. "Data Analyst"), location, and experience range.
Salary (`salaries`) is intentionally ignored.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from ..models import BronzeJob
from .base import BaseConnector

log = logging.getLogger("pipeline.ingest.glints")

_GQL_URL = "https://glints.com/api/v2/graphql"

# Glints free-text search massively over-matches (a "power bi" query returns sales/BD
# roles). Keep only rows whose job category OR title is genuinely Data-domain.
_DATA_RE = re.compile(
    r"\b(data\s*(analyst|engineer|scientist|analytics|architect|warehouse)"
    r"|machine\s*learning|ml\s*engineer|mlops|business\s*intelligence"
    r"|analytics\s*engineer|big\s*data|data\s*science|ai\s*engineer)\b",
    re.I,
)
_QUERY = """
query searchJobs($data: JobSearchConditionInput!) {
  searchJobs(data: $data) {
    hasMore
    jobsInPage {
      id title workArrangementOption status createdAt educationLevel type
      minYearsOfExperience maxYearsOfExperience
      company { id name brandName }
      location { name administrativeLevelName }
      citySubDivision { name }
      city { name }
      hierarchicalJobCategory { name level }
      skills { skill { name } mustHave }
    }
  }
}
""".strip()


class GlintsConnector(BaseConnector):
    source = "glints"

    def __init__(self, run_date: str | None = None):
        super().__init__(run_date)
        # Glints' GraphQL anti-bot needs a stable UA, the web-app headers, and a session
        # cookie. Configure the shared session once; cookies are seeded lazily.
        self.client.cfg["rotate_user_agent"] = False
        self.client.session.headers.update({
            "Origin": "https://glints.com",
            "Referer": "https://glints.com/vn/opportunities/jobs/explore",
            "apollographql-client-name": "glints-web",
            "x-glints-country-code": "VN",
        })
        self._bootstrapped = False

    def _ensure_bootstrap(self) -> None:
        if not self._bootstrapped:
            try:
                self.client.session.get("https://glints.com/vn", timeout=30)
            except Exception as exc:  # noqa: BLE001
                log.warning("glints cookie bootstrap failed: %s", exc)
            self._bootstrapped = True

    def _start_page(self) -> int:
        return 1

    def _page_size(self) -> int:
        return int(self.client.cfg.get("page_size", 50))

    def _gql_url(self) -> str:
        return self.client.cfg.get("graphql_api", _GQL_URL)

    def fetch_listing(self, category: str, page: int = 1) -> list[BronzeJob]:
        self._ensure_bootstrap()
        hits = self._search(category, page)
        jobs = [self._parse_job(j, category) for j in hits]
        # Drop non-Data noise from fuzzy keyword matching; keep genuine Data roles.
        return [j for j in jobs if self._is_data_role(j)]

    @staticmethod
    def _is_data_role(job: BronzeJob) -> bool:
        cat = job.extra.get("role_category_hint") or ""
        return bool(_DATA_RE.search(cat) or _DATA_RE.search(job.title_raw or ""))

    def scrape_all(self, jd_limit: int = 0) -> tuple[list[BronzeJob], dict]:
        """Override: paginate on the RAW result count (the Data filter shrinks pages, so
        the base 'stop when page < size' logic would quit after page 1)."""
        self._ensure_bootstrap()
        size, maxp = self._page_size(), self._max_pages()
        rows: dict[str, BronzeJob] = {}
        stats = {"pages_fetched": 0, "errors": 0, "per_item": {}, "jd_fetched": 0,
                 "raw_seen": 0}
        for term in self._scrape_items():
            n_before = len(rows)
            page = 1
            while page <= maxp:
                try:
                    raw = self._search(term, page)
                    stats["pages_fetched"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    log.warning("glints '%s' p%d failed: %s", term, page, exc)
                    break
                if not raw:
                    break
                stats["raw_seen"] += len(raw)
                for j in raw:
                    bj = self._parse_job(j, term)
                    if self._is_data_role(bj):
                        rows.setdefault(bj.source_job_id, bj)
                if len(raw) < size:
                    break
                page += 1
            stats["per_item"][term] = len(rows) - n_before
        return list(rows.values()), stats

    def _search(self, term: str, page: int) -> list[dict]:
        # Glints paginates via limit+offset (page/pageSize are ignored). page is 1-based.
        size = self._page_size()
        offset = (page - 1) * size
        variables = {"data": {
            "SearchTerm": [term], "CountryCode": ["VN"], "limit": size, "offset": offset,
        }}
        body = {"operationName": "searchJobs", "variables": variables, "query": _QUERY}
        safe = term.lower().replace(" ", "-")
        res = self.client.fetch(self._gql_url(), f"search_{safe}_p{page}.json",
                                method="POST", json_body=body)
        d = json.loads(res.text)
        sj = (d.get("data") or {}).get("searchJobs") or {}
        return sj.get("jobsInPage", [])

    def _parse_job(self, j: dict, term: str) -> BronzeJob:
        company = j.get("company") or {}
        loc = j.get("location") or {}
        csd = j.get("citySubDivision") or {}
        city = j.get("city") or {}
        location_raw = loc.get("name") or csd.get("name") or city.get("name")
        skills = [s["skill"]["name"] for s in (j.get("skills") or [])
                  if s.get("skill") and s["skill"].get("name")]
        cat = (j.get("hierarchicalJobCategory") or {}).get("name")
        return BronzeJob(
            source=self.source,
            source_job_id=str(j.get("id")),
            title_raw=j.get("title"),
            company_raw=company.get("name") or company.get("brandName"),
            location_raw=location_raw,
            description_raw=None,  # JD needs a per-job GraphQL call; skipped this pass
            skills_raw=skills,
            posted_date_raw=j.get("createdAt"),  # absolute ISO datetime
            url=f"https://glints.com/vn/opportunities/jobs/{j.get('id')}",
            ingested_at=datetime.now(timezone.utc),
            extra={
                "query_seen_in": term,
                "role_category_hint": cat,  # clean role signal, e.g. "Data Analyst"
                "work_model_raw": j.get("workArrangementOption"),
                "education_level": j.get("educationLevel"),
                "min_years_exp": j.get("minYearsOfExperience"),
                "max_years_exp": j.get("maxYearsOfExperience"),
                "salary_status": "ignored_out_of_scope",
            },
        )

    _DETAIL_QUERY = ("query getJobById($id: String!){ getJobById(id:$id){ "
                     "id descriptionJsonString } }")

    @staticmethod
    def _walk_text(node, out: list) -> None:
        if isinstance(node, dict):
            t = node.get("text")
            if isinstance(t, str) and t.strip():
                out.append(t)
            for v in node.values():
                GlintsConnector._walk_text(v, out)
        elif isinstance(node, list):
            for v in node:
                GlintsConnector._walk_text(v, out)

    def fetch_detail(self, job: BronzeJob) -> BronzeJob:
        """Populate description_raw via the getJobById GraphQL query (Slate-style JSON)."""
        if job.description_raw:
            return job
        self._ensure_bootstrap()
        body = {"operationName": "getJobById", "query": self._DETAIL_QUERY,
                "variables": {"id": job.source_job_id}}
        try:
            res = self.client.fetch(self._gql_url(), f"detail_{job.source_job_id}.json",
                                    method="POST", json_body=body)
            d = (json.loads(res.text).get("data") or {}).get("getJobById") or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("glints detail %s failed: %s", job.source_job_id, exc)
            return job
        parts: list = []
        dj = d.get("descriptionJsonString")
        if dj:
            try:
                self._walk_text(json.loads(dj), parts)
            except Exception:  # noqa: BLE001
                pass
        text = " ".join(p.strip() for p in parts if p.strip())
        job.description_raw = text or None
        return job

    def estimate_volume(self) -> dict:
        per_q = {}
        for q in self.client.cfg.get("queries", ["data"]):
            try:
                per_q[q] = {"page1": len(self._search(q, 1))}
            except Exception as exc:  # noqa: BLE001
                per_q[q] = f"ERROR {exc}"
        return {"per_query": per_q}
