"""BaseAdapter: polite fetching with caching, delay, UA, and robots.txt checks.

Subclass contract:
    class FooAdapter(BaseAdapter):
        name = "foo"
        def fetch(self) -> list[dict]: ...

fetch() returns dicts matching the listings columns. Required keys:
source, source_id, url, title. Unknown values should be None.

If a site blocks scraping or requires JS, adapters must NOT fight it:
log a warning, return [], and provide fixtures/<source>_sample.json so the
pipeline is testable offline via fixtures mode (load_fixtures()).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_ROOT = os.path.join(REPO_ROOT, "data", "cache")
FIXTURES_DIR = os.path.join(REPO_ROOT, "fixtures")

USER_AGENT = "FlipRadar/0.1 (personal deal research)"
REQUEST_DELAY_SECONDS = 2.0
CACHE_TTL_SECONDS = 12 * 3600

log = logging.getLogger("flipradar.adapters")


class BaseAdapter:
    """Base class for all listing-source adapters."""

    name: str = "base"  # override; used for cache dir and fixtures filename

    def __init__(self, use_fixtures: bool = False):
        self.use_fixtures = use_fixtures
        self._last_request_ts: float = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    # ---- public API -----------------------------------------------------

    def fetch(self) -> list[dict]:
        """Return a list of listing dicts. Override in subclasses."""
        raise NotImplementedError

    def run(self) -> list[dict]:
        """Entry point used by the CLI: fixtures mode or live fetch."""
        if self.use_fixtures:
            return self.load_fixtures()
        try:
            return self.fetch()
        except Exception as exc:  # never let one adapter kill a scan
            log.warning("%s: fetch failed (%s); returning []", self.name, exc)
            return []

    def load_fixtures(self) -> list[dict]:
        path = os.path.join(FIXTURES_DIR, f"{self.name}_sample.json")
        if not os.path.exists(path):
            log.warning("%s: no fixtures file at %s", self.name, path)
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for item in data:
            item.setdefault("source", self.name)
            # Fixtures are hand-written sample data with fabricated URLs —
            # label them so they can never be mistaken for real listings.
            title = item.get("title") or ""
            if not title.startswith("[SAMPLE]"):
                item["title"] = f"[SAMPLE] {title}"
        return data

    # ---- polite fetch helper -------------------------------------------

    def polite_get(self, url: str, force: bool = False) -> str | None:
        """GET a URL politely.

        - serves from data/cache/<source>/ when fresh (12h TTL)
        - respects robots.txt disallows (returns None, logs warning)
        - enforces a 2s delay between live requests (single-threaded)
        - custom User-Agent
        Returns response text, or None on block/error.
        """
        cached = None if force else self._cache_read(url)
        if cached is not None:
            return cached

        if not self._robots_allowed(url):
            log.warning("%s: robots.txt disallows %s", self.name, url)
            return None

        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
        except requests.RequestException as exc:
            log.warning("%s: request error for %s (%s)", self.name, url, exc)
            return None

        if resp.status_code in (403, 429):
            log.warning("%s: blocked (%s) at %s; not retrying", self.name, resp.status_code, url)
            return None
        if not resp.ok:
            log.warning("%s: HTTP %s at %s", self.name, resp.status_code, url)
            return None

        self._cache_write(url, resp.text)
        return resp.text

    # ---- internals ------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_ts = time.time()

    def _robots_allowed(self, url: str) -> bool:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(url))
        rp = self._robots.get(origin)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(origin + "/robots.txt")
            try:
                self._throttle()
                resp = self.session.get(origin + "/robots.txt", timeout=15)
                if resp.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(resp.text.splitlines())
            except requests.RequestException:
                rp.allow_all = True  # unreachable robots.txt -> assume allowed
            self._robots[origin] = rp
        return rp.can_fetch(USER_AGENT, url)

    def _cache_path(self, url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return os.path.join(CACHE_ROOT, self.name, digest + ".html")

    def _cache_read(self, url: str) -> str | None:
        path = self._cache_path(url)
        try:
            if time.time() - os.path.getmtime(path) > CACHE_TTL_SECONDS:
                return None
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def _cache_write(self, url: str, text: str) -> None:
        path = self._cache_path(url)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
