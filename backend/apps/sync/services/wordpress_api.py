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
_UNSET = object()


class WordPressAPIClient:
    """Fetch WordPress posts/pages with optional Application Password auth."""

    def __init__(
        self,
        base_url: str | object = _UNSET,
        username: str | object = _UNSET,
        app_password: str | object = _UNSET,
    ) -> None:
        use_settings_fallbacks = (
            base_url is _UNSET
            and username is _UNSET
            and app_password is _UNSET
        )
        if use_settings_fallbacks:
            resolved_base_url = getattr(settings, "WORDPRESS_BASE_URL", "")
            resolved_username = getattr(settings, "WORDPRESS_USERNAME", "")
            resolved_app_password = getattr(settings, "WORDPRESS_APP_PASSWORD", "")
        else:
            resolved_base_url = "" if base_url is _UNSET else (base_url or "")
            resolved_username = "" if username is _UNSET else (username or "")
            resolved_app_password = "" if app_password is _UNSET else (app_password or "")

        self.base_url = str(resolved_base_url).strip().rstrip("/")
        self.username = str(resolved_username).strip()
        self.app_password = str(resolved_app_password).strip()

        if not self.base_url:
            raise ValueError("WordPress base URL is missing (check WORDPRESS_BASE_URL or saved settings).")

        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "XF Internal Linker V2"})
        if self.username and self.app_password:
            self.session.auth = HTTPBasicAuth(self.username, self.app_password)

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.app_password)

    def verify_credentials(self) -> dict[str, Any]:
        """Call /wp-json/wp/v2/users/me to confirm credentials are accepted.

        Returns {'ok': True, 'display_name': str} on success.
        Returns {'ok': False, 'display_name': ''} on HTTP 401.
        Raises for any other network or HTTP error.
        """
        resp = self.session.get(f"{self.base_url}/wp-json/wp/v2/users/me", timeout=10)
        if resp.status_code == 401:
            return {"ok": False, "display_name": ""}
        resp.raise_for_status()
        data = resp.json()
        return {"ok": True, "display_name": data.get("name", "")}

    def get_posts(self, page: int = 1, *, status: str = "publish", after: str | None = None) -> tuple[list[dict[str, Any]], int]:
        """Fetch one page of WordPress posts."""
        return self._list_endpoint("posts", page=page, status=status, after=after)

    def get_pages(self, page: int = 1, *, status: str = "publish", after: str | None = None) -> tuple[list[dict[str, Any]], int]:
        """Fetch one page of WordPress pages."""
        return self._list_endpoint("pages", page=page, status=status, after=after)

    def get_post(self, post_id: int) -> dict[str, Any]:
        """Fetch a single post by ID."""
        return self._get(f"posts/{post_id}").json()

    def get_page(self, page_id: int) -> dict[str, Any]:
        """Fetch a single page by ID."""
        return self._get(f"pages/{page_id}").json()

    def iter_posts(self, *, after: str | None = None) -> Iterator[dict[str, Any]]:
        """Yield published posts plus private posts when credentials are configured."""
        yield from self._iter_endpoint("posts", after=after)

    def iter_pages(self, *, after: str | None = None) -> Iterator[dict[str, Any]]:
        """Yield published pages plus private pages when credentials are configured."""
        yield from self._iter_endpoint("pages", after=after)

    def _iter_endpoint(self, endpoint: str, *, after: str | None = None) -> Iterator[dict[str, Any]]:
        seen_ids: set[int] = set()

        for status in self._statuses_for_fetch():
            page = 1
            total_pages = 1
            while page <= total_pages:
                records, total_pages = self._list_endpoint(endpoint, page=page, status=status, after=after)
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

    def _list_endpoint(self, endpoint: str, *, page: int, status: str, after: str | None = None) -> tuple[list[dict[str, Any]], int]:
        params = {
            "page": page,
            "per_page": _PER_PAGE,
            "status": status,
        }
        if after:
            params["after"] = after
            
        response = self._get(
            endpoint,
            params=params,
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
