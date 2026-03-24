"""Read-only WordPress REST API client used for cross-link indexing."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

_PER_PAGE = 100


class WordPressAPIClient:
    """Fetch WordPress posts/pages with optional Application Password auth."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "WORDPRESS_BASE_URL", "")).strip().rstrip("/")
        self.username = (username if username is not None else getattr(settings, "WORDPRESS_USERNAME", "")).strip()
        self.app_password = (
            app_password if app_password is not None else getattr(settings, "WORDPRESS_APP_PASSWORD", "")
        ).strip()

        if not self.base_url:
            raise ValueError("WordPress base URL is missing (check WORDPRESS_BASE_URL or saved settings).")

        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "XF Internal Linker V2"})
        if self.username and self.app_password:
            self.session.auth = HTTPBasicAuth(self.username, self.app_password)

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.app_password)

    def get_posts(self, page: int = 1, *, status: str = "publish") -> tuple[list[dict[str, Any]], int]:
        """Fetch one page of WordPress posts."""
        return self._list_endpoint("posts", page=page, status=status)

    def get_pages(self, page: int = 1, *, status: str = "publish") -> tuple[list[dict[str, Any]], int]:
        """Fetch one page of WordPress pages."""
        return self._list_endpoint("pages", page=page, status=status)

    def iter_posts(self) -> Iterator[dict[str, Any]]:
        """Yield published posts plus private posts when credentials are configured."""
        yield from self._iter_endpoint("posts")

    def iter_pages(self) -> Iterator[dict[str, Any]]:
        """Yield published pages plus private pages when credentials are configured."""
        yield from self._iter_endpoint("pages")

    def _iter_endpoint(self, endpoint: str) -> Iterator[dict[str, Any]]:
        seen_ids: set[int] = set()

        for status in self._statuses_for_fetch():
            page = 1
            total_pages = 1
            while page <= total_pages:
                records, total_pages = self._list_endpoint(endpoint, page=page, status=status)
                if not records:
                    break
                for record in records:
                    record_id = int(record.get("id") or 0)
                    if not record_id or record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)
                    yield record
                page += 1

    def _statuses_for_fetch(self) -> tuple[str, ...]:
        if self.has_credentials:
            return ("publish", "private")
        return ("publish",)

    def _list_endpoint(self, endpoint: str, *, page: int, status: str) -> tuple[list[dict[str, Any]], int]:
        response = self._get(
            endpoint,
            params={
                "page": page,
                "per_page": _PER_PAGE,
                "status": status,
            },
        )
        total_pages = int(response.headers.get("X-WP-TotalPages", "1") or "1")
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"Unexpected WordPress {endpoint} response shape.")
        return payload, max(total_pages, 1)

    def _get(self, endpoint: str, *, params: dict[str, Any] | None = None) -> requests.Response:
        url = f"{self.base_url}/wp-json/wp/v2/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error("WordPress API request failed: %s (URL: %s)", exc, url)
            raise
