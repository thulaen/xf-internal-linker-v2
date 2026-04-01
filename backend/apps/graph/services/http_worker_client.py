"""Thin optional client for the HttpWorker helper service."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from django.conf import settings


class HttpWorkerError(Exception):
    """Raised when the helper service returns an error or cannot be reached."""


class HttpWorkerDisabledError(HttpWorkerError):
    """Raised when the helper service is turned off in Django settings."""


def _base_url() -> str:
    enabled = getattr(settings, "HTTP_WORKER_ENABLED", False)
    if not enabled:
        raise HttpWorkerDisabledError("HttpWorker is disabled")
    base_url = getattr(settings, "HTTP_WORKER_URL", "http://http-worker-api:8080").rstrip("/")
    if base_url.endswith("/api/v1/status"):
        return base_url[: -len("/api/v1/status")]
    return base_url


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=60) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise HttpWorkerError(f"HttpWorker returned status {exc.code}") from exc
    except error.URLError as exc:
        raise HttpWorkerError(f"HttpWorker request failed: {exc}") from exc

    if status_code != 200:
        raise HttpWorkerError(f"HttpWorker returned status {status_code}")

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise HttpWorkerError("HttpWorker returned invalid JSON") from exc


def check_broken_links(items: list[dict]) -> list[dict]:
    payload = {
        "urls": items,
        "user_agent": "XF Internal Linker V2",
        "timeout_seconds": 10,
        "max_concurrency": 50,
    }
    data = _post_json("/api/v1/broken-links/check", payload)
    return data.get("checked", [])


def check_health(urls: list[str]) -> list[dict]:
    payload = {
        "urls": urls,
        "timeout_seconds": 5,
        "max_concurrency": 100,
    }
    data = _post_json("/api/v1/health/check", payload)
    return data.get("checked", [])


def crawl_sitemap(sitemap_url: str, max_urls: int = 10000) -> list[dict]:
    payload = {
        "sitemap_url": sitemap_url,
        "headers": {},
        "timeout_seconds": 30,
        "max_urls": max_urls,
    }
    data = _post_json("/api/v1/sitemaps/crawl", payload)
    return data.get("discovered_urls", [])
