"""Thin optional client for the HttpWorker helper service."""

from __future__ import annotations

from datetime import datetime, timezone
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


def _request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    accepted_status_codes: set[int] | None = None,
) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with request.urlopen(http_request, timeout=60) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise HttpWorkerError(f"HttpWorker returned status {exc.code}") from exc
    except error.URLError as exc:
        raise HttpWorkerError(f"HttpWorker request failed: {exc}") from exc

    accepted_status_codes = accepted_status_codes or {200}
    if status_code not in accepted_status_codes:
        raise HttpWorkerError(f"HttpWorker returned status {status_code}")

    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise HttpWorkerError("HttpWorker returned invalid JSON") from exc


def _post_json(
    path: str,
    payload: dict[str, Any],
    *,
    accepted_status_codes: set[int] | None = None,
) -> dict[str, Any]:
    return _request_json(
        "POST",
        path,
        payload,
        accepted_status_codes=accepted_status_codes,
    )


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


def queue_job(job_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = {
        "schema_version": getattr(settings, "HTTP_WORKER_SCHEMA_VERSION", "v1"),
        "job_id": job_id,
        "job_type": job_type,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "payload": payload,
    }
    return _post_json(
        "/api/v1/jobs",
        request_payload,
        accepted_status_codes={202},
    )


def sync_graph_content(
    *,
    content_item_pk: int,
    content_id: int,
    content_type: str,
    raw_bbcode: str,
    forum_domains: list[str],
    allow_disappearance: bool = True,
    tracked_at: datetime | None = None,
) -> dict[str, Any]:
    payload = {
        "content_item_pk": content_item_pk,
        "content_id": content_id,
        "content_type": content_type,
        "raw_bbcode": raw_bbcode,
        "forum_domains": forum_domains,
        "allow_disappearance": allow_disappearance,
    }
    if tracked_at is not None:
        payload["tracked_at"] = tracked_at.astimezone(timezone.utc).isoformat()
    return _post_json("/api/v1/graph-sync/content", payload)


def refresh_graph_links(
    *,
    forum_domains: list[str],
    content_item_pks: list[int] | None = None,
    tracked_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "forum_domains": forum_domains,
    }
    if content_item_pks:
        payload["content_item_pks"] = content_item_pks
    if tracked_at is not None:
        payload["tracked_at"] = tracked_at.astimezone(timezone.utc).isoformat()
    return _post_json("/api/v1/graph-sync/refresh", payload)
