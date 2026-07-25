"""Thin HTTP layer over The Movie Database (TMDB) v3 API.

This module owns everything network-shaped: building requests, injecting
the API key, retrying on rate limits, and translating HTTP-level failures
into a small typed exception hierarchy. It knows nothing about SQLAlchemy
or this application's models -- callers get back plain dicts/lists exactly
as TMDB returns them. Mapping that JSON onto `Project`/`Person`/etc. lives
in `services/tmdb_sync_service.py`.

TMDB API docs: https://developer.themoviedb.org/docs
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 3

# Used only as a last-resort fallback if a live `/search/company` lookup for
# "Marvel Studios" comes back empty (e.g. a transient TMDB hiccup) -- the
# sync service always tries the live lookup first. TMDB's id for Marvel
# Studios has been stable for years, but the live lookup is the source of
# truth so this app never silently drifts if that ever changes.
MARVEL_STUDIOS_FALLBACK_COMPANY_ID = 420

# Same idea, for the 2013-2020 "Marvel Television" production label (Agents
# of S.H.I.E.L.D., Agent Carter, the Netflix Defenders shows, ...). This is
# a *different* TMDB company from Marvel Studios -- discovering only company
# 420 is why that whole slate was previously missing from every sync.
MARVEL_TELEVISION_FALLBACK_COMPANY_ID = 38679


class TMDBError(Exception):
    """Base class for every error this client raises."""


class TMDBAuthError(TMDBError):
    """The API key is missing, malformed, or rejected by TMDB (HTTP 401)."""


class TMDBNotFoundError(TMDBError):
    """The requested resource doesn't exist on TMDB (HTTP 404)."""


class TMDBRateLimitError(TMDBError):
    """TMDB kept returning HTTP 429 after every retry was exhausted."""


class TMDBConnectionError(TMDBError):
    """A network-level failure (timeout, DNS, connection refused, ...)."""


def image_url(path: str | None, *, size: str = "w500") -> str | None:
    """Build a full poster/backdrop/profile image URL from a TMDB-relative
    path (e.g. ``/abc123.jpg``). Returns ``None`` if ``path`` is falsy, so
    callers can pass a possibly-absent field straight through."""
    if not path:
        return None
    return f"{DEFAULT_IMAGE_BASE_URL}/{size}{path}"


class TMDBClient:
    """A small, synchronous TMDB v3 client using an API key (not a bearer
    read-access token) since that's the credential shape most people think
    of as "an API key" and what the Settings page collects.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise TMDBAuthError("No TMDB API key configured.")

        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    # --- low-level request plumbing -----------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_params = dict(params or {})
        request_params["api_key"] = self.api_key

        attempt = 0
        while True:
            attempt += 1
            try:
                response = self.session.get(url, params=request_params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise TMDBConnectionError(f"Could not reach TMDB: {exc}") from exc

            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                raise TMDBAuthError("TMDB rejected the API key (HTTP 401).")

            if response.status_code == 404:
                raise TMDBNotFoundError(f"TMDB resource not found: {path}")

            if response.status_code == 429:
                if attempt > self.max_retries:
                    raise TMDBRateLimitError(
                        f"TMDB rate limit exceeded after {self.max_retries} retries."
                    )
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                logger.warning(
                    "TMDB rate limited (attempt %s/%s); retrying in %.1fs",
                    attempt,
                    self.max_retries,
                    retry_after,
                )
                time.sleep(retry_after)
                continue

            raise TMDBError(f"TMDB request to {path} failed: HTTP {response.status_code}")

    @staticmethod
    def _parse_retry_after(raw: str | None) -> float:
        if not raw:
            return 1.0
        try:
            return max(0.5, float(raw))
        except ValueError:
            return 1.0

    # --- companies -----------------------------------------------------------

    def search_company(self, query: str) -> list[dict[str, Any]]:
        """Search TMDB companies by name. Used to resolve "Marvel Studios"
        to a live company id rather than trusting a hardcoded constant."""
        data = self._get("/search/company", {"query": query})
        return data.get("results", [])

    # --- discovery (bulk listing by company) ---------------------------------

    def discover_movies(self, company_id: int, *, page: int = 1) -> dict[str, Any]:
        """One page of movies produced by ``company_id``, sorted by release
        date so pagination reads chronologically. Returns the raw TMDB
        paginated response (``results``, ``page``, ``total_pages``, ...)."""
        return self._get(
            "/discover/movie",
            {
                "with_companies": company_id,
                "page": page,
                "sort_by": "primary_release_date.asc",
                "include_adult": "false",
            },
        )

    def discover_tv(self, company_id: int, *, page: int = 1) -> dict[str, Any]:
        """One page of TV series produced by ``company_id``. Mirrors
        `discover_movies`, see its docstring."""
        return self._get(
            "/discover/tv",
            {
                "with_companies": company_id,
                "page": page,
                "sort_by": "first_air_date.asc",
                "include_adult": "false",
            },
        )

    # --- details (single item, with credits) ---------------------------------

    def get_movie_details(self, movie_id: int) -> dict[str, Any]:
        """Full movie record including embedded ``credits`` (cast + crew)
        and ``videos`` (trailers, teasers, ...) objects, fetched in one
        round trip via ``append_to_response``."""
        return self._get(f"/movie/{movie_id}", {"append_to_response": "credits,videos"})

    def get_tv_details(self, tv_id: int) -> dict[str, Any]:
        """Full TV record including embedded ``credits`` and ``videos``
        objects. Note TMDB's TV credits endpoint returns *aggregate*
        cast/crew across all seasons, which is what
        `append_to_response=credits` gives here."""
        return self._get(f"/tv/{tv_id}", {"append_to_response": "credits,videos"})

    # --- search (manual lookups / fallback) -----------------------------------

    def search_movie(self, query: str) -> list[dict[str, Any]]:
        data = self._get("/search/movie", {"query": query, "include_adult": "false"})
        return data.get("results", [])

    def search_tv(self, query: str) -> list[dict[str, Any]]:
        data = self._get("/search/tv", {"query": query, "include_adult": "false"})
        return data.get("results", [])
