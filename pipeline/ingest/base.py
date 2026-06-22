"""Connector interface shared by all source connectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date

from ..models import BronzeJob
from ..utils.http import LiveFetchCapReached, ScrapeClient

log = logging.getLogger("pipeline.ingest")


class BaseConnector(ABC):
    source: str

    def __init__(self, run_date: str | None = None):
        self.run_date = run_date or date.today().isoformat()
        self.client = ScrapeClient.for_source(self.source, run_date=self.run_date)

    @abstractmethod
    def fetch_listing(self, category: str, page: int) -> list[BronzeJob]:
        """Fetch one listing page/query and return parsed (un-normalized) Bronze rows."""

    @abstractmethod
    def estimate_volume(self) -> dict:
        """Return a volume estimate for this source's Data postings."""

    # --- pagination hooks (overridden per source) --------------------------
    def _scrape_items(self) -> list[str]:
        """Categories (ITviec) or search queries (TopDev/VNW) to sweep."""
        return self.client.cfg.get("categories") or self.client.cfg.get("queries") or []

    def _start_page(self) -> int:
        return 1

    def _page_size(self) -> int:
        return int(self.client.cfg.get("cards_per_page")
                   or self.client.cfg.get("hits_per_page") or 20)

    def _max_pages(self) -> int:
        return int(self.client.cfg.get("max_pages_per_category")
                   or self.client.cfg.get("max_pages_per_query") or 10)

    # --- full scrape with dedup + optional JD fetch ------------------------
    def scrape_all(self, jd_limit: int = 0) -> tuple[list[BronzeJob], dict]:
        items, start, size, maxp = (
            self._scrape_items(), self._start_page(), self._page_size(), self._max_pages()
        )
        rows: dict[str, BronzeJob] = {}
        stats = {"pages_fetched": 0, "errors": 0, "per_item": {}, "jd_fetched": 0}
        for item in items:
            n_before = len(rows)
            page = start
            while page < start + maxp:
                try:
                    batch = self.fetch_listing(item, page)
                    stats["pages_fetched"] += 1
                except LiveFetchCapReached as exc:
                    stats["cap_reached"] = True
                    log.warning("%s: %s", self.source, exc)
                    break
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    log.warning("%s '%s' p%d failed: %s", self.source, item, page, exc)
                    break
                if not batch:
                    break
                for j in batch:
                    rows.setdefault(j.source_job_id, j)
                if len(batch) < size:
                    break
                page += 1
            stats["per_item"][item] = len(rows) - n_before  # NEW distinct added by this item
        # ITviec needs a per-job JD fetch; API sources already carry the JD inline.
        if jd_limit and hasattr(self, "fetch_detail"):
            for j in list(rows.values())[:jd_limit]:
                if self.client._live_fetches >= self.client.max_live_fetches:
                    stats["cap_reached"] = True
                    log.warning("%s: live-fetch cap hit; stopping JD fetch after %d",
                                self.source, stats["jd_fetched"])
                    break
                self.fetch_detail(j)  # type: ignore[attr-defined]
                stats["jd_fetched"] += 1
        return list(rows.values()), stats
