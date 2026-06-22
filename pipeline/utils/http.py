"""Responsible-scraping HTTP client.

Enforces the project's scraping rules in one place:
  * respect robots.txt (cached per host),
  * randomized 3-8s delay between *live* fetches,
  * rotated User-Agent,
  * route through ScraperAPI (with key rotation + backoff), optional direct fallback,
  * cache every raw response to data/raw/ immediately, so re-runs are resumable
    and never re-fetch a URL already on disk.
"""

from __future__ import annotations

import logging
import random
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests

from .config import RAW_DIR, Secrets, get_secrets, source_config

log = logging.getLogger("pipeline.http")

# A small rotation pool of realistic desktop User-Agents.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com/"


class LiveFetchCapReached(RuntimeError):
    """Raised when the per-run live ScraperAPI fetch cap is hit (credit guardrail)."""


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    from_cache: bool
    via: str  # "cache" | "scraperapi" | "direct"
    cache_path: Path | None = None


@dataclass
class ScrapeClient:
    """Per-source client. Construct via ``ScrapeClient.for_source(name)``."""

    source: str
    cfg: dict
    secrets: Secrets
    run_date: str
    session: requests.Session = field(default_factory=requests.Session)
    _robots: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)
    _key_idx: int = 0
    # Credit guardrails
    max_live_fetches: int = 10**9   # hard cap on live ScraperAPI fetches per client
    _live_fetches: int = 0
    _usable_keys: list[str] | None = None

    @classmethod
    def for_source(cls, source: str, run_date: str | None = None) -> "ScrapeClient":
        return cls(
            source=source,
            cfg=source_config(source),
            secrets=get_secrets(),
            run_date=run_date or date.today().isoformat(),
        )

    # --- robots.txt ---------------------------------------------------------
    def _robots_parser(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urllib.parse.urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{host}/robots.txt")
            # Fetch robots.txt ourselves with a real UA. RobotFileParser.read() uses the
            # default Python-urllib UA, which some sites (ITviec) 403 -> parser then
            # treats the whole site as disallowed. Fetching with a browser UA avoids that.
            try:
                resp = self.session.get(
                    f"{host}/robots.txt", headers=self._headers(), timeout=20
                )
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    log.warning("robots.txt %s -> HTTP %d; assuming allowed", host, resp.status_code)
                    rp.allow_all = True
            except Exception as exc:  # network/parse failure -> fail open but log
                log.warning("robots.txt fetch failed for %s (%s); assuming allowed", host, exc)
                rp.allow_all = True
            self._robots[host] = rp
        return self._robots[host]

    def allowed(self, url: str) -> bool:
        if not self.cfg.get("respect_robots", True):
            return True
        ua = "*"
        return self._robots_parser(url).can_fetch(ua, url)

    # --- caching ------------------------------------------------------------
    def _cache_path(self, name: str) -> Path:
        # Raw cache is a flat, date-less, content-by-URL store (the cache_name encodes
        # the URL). It is purely for resumability/reproducibility and carries no temporal
        # meaning — snapshots live in the dated Bronze layer, not here. Date-less means a
        # run_date rollover never re-fetches and the same response is never duplicated.
        return RAW_DIR / self.source / name

    def _read_cache(self, path: Path) -> str | None:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return None

    def _write_cache(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", errors="replace")

    # --- delay / UA ---------------------------------------------------------
    def _sleep(self) -> None:
        lo = float(self.cfg.get("min_delay_seconds", 3))
        hi = float(self.cfg.get("max_delay_seconds", 8))
        time.sleep(random.uniform(lo, hi))

    def _headers(self) -> dict:
        ua = random.choice(USER_AGENTS) if self.cfg.get("rotate_user_agent", True) else USER_AGENTS[0]
        return {"User-Agent": ua, "Accept-Language": "en,vi;q=0.8"}

    @staticmethod
    def key_credits_left(key: str) -> int | None:
        """Remaining ScraperAPI credits for a key (None if the check fails)."""
        try:
            r = requests.get("https://api.scraperapi.com/account",
                             params={"api_key": key}, timeout=30)
            if r.status_code == 200:
                d = r.json()
                return int(d.get("requestLimit", 0)) - int(d.get("requestCount", 0))
        except Exception:  # noqa: BLE001
            return None
        return None

    def _get_usable_keys(self) -> list[str]:
        """Keys with enough credits, computed once. Drops near-empty keys (protects a
        nearly-exhausted secondary); falls back to all keys if the check fails or all
        are low, so a flaky account check never hard-blocks a run."""
        if self._usable_keys is not None:
            return self._usable_keys
        all_keys = self.secrets.keys
        threshold = int(self.cfg.get("min_key_credits", 50))
        usable, info = [], []
        for k in all_keys:
            left = self.key_credits_left(k)
            info.append(f"{k[:6]}…={left}")
            if left is None or left >= threshold:
                usable.append(k)
            else:
                log.warning("dropping ScraperAPI key %s… (%s credits < %d threshold)",
                            k[:6], left, threshold)
        self._usable_keys = usable or all_keys  # never end up with zero keys
        log.info("ScraperAPI keys: %s -> using %d/%d", ", ".join(info),
                 len(self._usable_keys), len(all_keys))
        return self._usable_keys

    def _next_key(self) -> str | None:
        keys = self._get_usable_keys()
        if not keys:
            return None
        key = keys[self._key_idx % len(keys)]
        self._key_idx += 1
        return key

    # --- fetch --------------------------------------------------------------
    def fetch(
        self,
        url: str,
        cache_name: str,
        method: str = "GET",
        json_body: dict | None = None,
    ) -> FetchResult:
        """Fetch ``url``, caching to ``data/raw/<source>/<run_date>/<cache_name>``.

        Returns cached content with no network call if already on disk. Supports POST
        with a JSON body (for JSON search APIs); non-GET requests always go direct
        (ScraperAPI is used only for GET HTML scraping here).
        """
        path = self._cache_path(cache_name)
        cached = self._read_cache(path)
        if cached is not None:
            log.info("cache hit  %s", cache_name)
            return FetchResult(url, 200, cached, True, "cache", path)

        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")

        timeout = float(self.cfg.get("request_timeout_seconds", 45))
        retries = int(self.cfg.get("max_retries", 3))
        is_get = method.upper() == "GET"
        use_api = is_get and self.cfg.get("use_scraperapi", True) and bool(self.secrets.keys)

        # Credit guardrail: cap live ScraperAPI fetches so a cache miss can't silently
        # burn hundreds of credits (cache hits above never reach here, so don't count).
        if use_api:
            if self._live_fetches >= self.max_live_fetches:
                raise LiveFetchCapReached(
                    f"live ScraperAPI fetch cap ({self.max_live_fetches}) reached; "
                    f"skipping {cache_name}"
                )
            self._live_fetches += 1

        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            self._sleep()  # throttle every live attempt
            try:
                if use_api:
                    res = self._fetch_scraperapi(url, timeout)
                    via = "scraperapi"
                else:
                    res = self.session.request(
                        method, url, headers=self._headers(), json=json_body, timeout=timeout
                    )
                    via = "direct"
                if res.status_code == 200 and res.text:
                    self._write_cache(path, res.text)
                    log.info("fetched %s via %s (%d bytes)", cache_name, via, len(res.text))
                    return FetchResult(url, res.status_code, res.text, False, via, path)
                last_exc = RuntimeError(f"HTTP {res.status_code} via {via}")
                log.warning("attempt %d/%d %s -> %s", attempt, retries, cache_name, last_exc)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("attempt %d/%d %s error: %s", attempt, retries, cache_name, exc)
            time.sleep(min(2**attempt, 10))  # backoff

        # ScraperAPI exhausted -> optional direct fallback.
        if use_api and self.cfg.get("allow_direct_fallback", True):
            log.warning("ScraperAPI failed for %s; falling back to direct fetch", cache_name)
            self._sleep()
            res = self.session.get(url, headers=self._headers(), timeout=timeout)
            if res.status_code == 200 and res.text:
                self._write_cache(path, res.text)
                return FetchResult(url, res.status_code, res.text, False, "direct", path)

        raise RuntimeError(f"failed to fetch {url}: {last_exc}")

    def _fetch_scraperapi(self, url: str, timeout: float) -> requests.Response:
        key = self._next_key()
        params = {"api_key": key, "url": url}
        # Geotargeting (country_code) is a paid ScraperAPI feature; on the free plan it
        # 500s. Only send it when explicitly configured. ITviec serves the same content
        # without it.
        country = self.cfg.get("scraperapi_country_code")
        if country:
            params["country_code"] = country
        if self.cfg.get("scraperapi_render", False):
            params["render"] = "true"
        # ScraperAPI itself can be slow; allow extra time on top of the target timeout.
        return self.session.get(
            SCRAPERAPI_ENDPOINT, params=params, headers=self._headers(), timeout=timeout + 30
        )
