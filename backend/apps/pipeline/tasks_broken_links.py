"""Extracted helpers for the scan_broken_links Celery task.

Pure structural refactoring -- no behavior change.  Every function here was
previously inlined inside ``scan_broken_links`` in ``tasks.py``.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from apps.pipeline.tasks import (
    _MAX_BROKEN_LINK_SCAN_URLS,
    _publish_progress,
    _status_label,
)
try:
    from apps.pipeline.services.async_http import probe_urls, run_async
except ImportError:
    probe_urls = None  # type: ignore[assignment]  # httpx only in Docker
    run_async = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

# Iterator batch sizes
_CHUNK_SIZE_LINKS = 250  # maxsize for ExistingLink iterator
_CHUNK_SIZE_POSTS = 100  # maxsize for Post iterator


def collect_urls_to_scan() -> tuple[dict[tuple[int, str], dict[str, Any]], bool]:
    """Gather URLs from ExistingLink and Post tables up to the scan cap.

    Returns ``(urls_to_scan_dict, hit_scan_cap)``.
    """
    from django.conf import settings

    from apps.content.models import Post
    from apps.graph.models import ExistingLink
    from apps.pipeline.services.link_parser import extract_urls

    allowed_domains: list[str] | None = None
    for raw_url in [
        getattr(settings, "XENFORO_BASE_URL", ""),
        getattr(settings, "WORDPRESS_BASE_URL", ""),
    ]:
        host = urlparse(raw_url).netloc.strip().lower()
        if host:
            if allowed_domains is None:
                allowed_domains = []
            if host not in allowed_domains:
                allowed_domains.append(host)

    urls_to_scan: dict[tuple[int, str], dict[str, Any]] = {}
    hit_scan_cap = False

    existing_links = (
        ExistingLink.objects.select_related("from_content_item", "to_content_item")
        .filter(from_content_item__is_deleted=False)
        .exclude(to_content_item__url="")
        .order_by("from_content_item_id", "to_content_item_id")
    )
    for link in existing_links.iterator(chunk_size=_CHUNK_SIZE_LINKS):
        if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
            hit_scan_cap = True
            break
        urls_to_scan.setdefault(
            (link.from_content_item_id, link.to_content_item.url),
            {
                "source_content_id": link.from_content_item_id,
                "url": link.to_content_item.url,
            },
        )

    if not hit_scan_cap:
        posts = (
            Post.objects.select_related("content_item")
            .filter(content_item__is_deleted=False)
            .exclude(raw_bbcode="")
            .order_by("content_item_id")
        )
        for post in posts.iterator(chunk_size=_CHUNK_SIZE_POSTS):
            if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
                hit_scan_cap = True
                break
            for url in extract_urls(post.raw_bbcode, allowed_domains=allowed_domains):
                urls_to_scan.setdefault(
                    (post.content_item_id, url),
                    {"source_content_id": post.content_item_id, "url": url},
                )
                if len(urls_to_scan) >= _MAX_BROKEN_LINK_SCAN_URLS:
                    hit_scan_cap = True
                    break

    return urls_to_scan, hit_scan_cap


def build_existing_records_map(
    urls_to_scan: dict[tuple[int, str], dict[str, Any]],
) -> dict[tuple[int, str], Any]:
    """Load existing BrokenLink rows that match the scan set."""
    from apps.graph.models import BrokenLink

    existing_qs = BrokenLink.objects.filter(
        source_content_id__in={
            source_content_id for source_content_id, _ in urls_to_scan.keys()
        },
        url__in={url for _, url in urls_to_scan.keys()},
    )
    return {(record.source_content_id, record.url): record for record in existing_qs}


def store_probe_result(
    *,
    source_content_id: int,
    url: str,
    http_status: int,
    redirect_url: str,
    existing_records: dict[tuple[int, str], Any],
    to_create: list[Any],
    to_update: list[Any],
    checked_at: Any,
) -> tuple[int, int]:
    """Classify a probe result and append to create/update lists.

    Returns ``(flagged_delta, fixed_delta)`` -- each is 0 or 1.
    """
    from apps.graph.models import BrokenLink

    existing_record = existing_records.get((source_content_id, url))
    issue_detected = http_status == 0 or bool(redirect_url) or http_status >= 300
    flagged_delta = 0
    fixed_delta = 0

    if issue_detected:
        flagged_delta = 1
        record_status = (
            BrokenLink.STATUS_IGNORED
            if existing_record and existing_record.status == BrokenLink.STATUS_IGNORED
            else BrokenLink.STATUS_OPEN
        )
        if existing_record is None:
            to_create.append(
                BrokenLink(
                    source_content_id=source_content_id,
                    url=url,
                    http_status=http_status,
                    redirect_url=redirect_url,
                    status=record_status,
                    notes="",
                    first_detected_at=checked_at,
                    last_checked_at=checked_at,
                )
            )
        else:
            existing_record.http_status = http_status
            existing_record.redirect_url = redirect_url
            existing_record.status = record_status
            existing_record.last_checked_at = checked_at
            to_update.append(existing_record)
    elif existing_record:
        fixed_delta = 1
        existing_record.http_status = http_status
        existing_record.redirect_url = ""
        existing_record.status = BrokenLink.STATUS_FIXED
        existing_record.last_checked_at = checked_at
        to_update.append(existing_record)

    return flagged_delta, fixed_delta


def scan_via_async_http(
    scan_items: list[dict[str, Any]],
    *,
    job_id: str,
    total_urls: int,
    existing_records: dict[tuple[int, str], Any],
    to_create: list[Any],
    to_update: list[Any],
    checked_at: Any,
    hit_scan_cap: bool,
) -> tuple[int, int, str]:
    """Scan all URLs concurrently via httpx.

    Returns ``(flagged_urls, fixed_urls, probe_backend)``.
    """
    flagged_urls = 0
    fixed_urls = 0
    probe_backend = "python_async_httpx"
    urls = [str(item["url"]) for item in scan_items]

    def progress_cb(completed: int, url: str, result: tuple[int, str]):
        nonlocal flagged_urls, fixed_urls
        http_status, redirect_url = result

        # We need the source_content_id. Let's find it.
        # However, the callback only gets URL. We might need to map it back or just let the main loop do the DB updates.
        pass

    results = run_async(probe_urls(urls, max_concurrency=50, on_progress=progress_cb))

    for index, scan_item in enumerate(scan_items, start=1):
        source_content_id = int(scan_item["source_content_id"])
        url = str(scan_item["url"])

        http_status, redirect_url = results.get(url, (0, ""))

        f_delta, x_delta = store_probe_result(
            source_content_id=source_content_id,
            url=url,
            http_status=http_status,
            redirect_url=redirect_url,
            existing_records=existing_records,
            to_create=to_create,
            to_update=to_update,
            checked_at=checked_at,
        )
        flagged_urls += f_delta
        fixed_urls += x_delta

        _publish_progress(
            job_id,
            "running",
            index / total_urls if total_urls else 0,
            f"Checked {index}/{total_urls}: {_status_label(http_status)}",
            scanned_urls=index,
            total_urls=total_urls,
            flagged_urls=flagged_urls,
            fixed_urls=fixed_urls,
            current_url=url,
            hit_scan_cap=hit_scan_cap,
            probe_backend=probe_backend,
        )

    return flagged_urls, fixed_urls, probe_backend


def persist_scan_results(
    to_create: list[Any],
    to_update: list[Any],
) -> None:
    """Bulk-write new and updated BrokenLink rows."""
    from apps.graph.models import BrokenLink

    if to_create:
        BrokenLink.objects.bulk_create(to_create)
    if to_update:
        BrokenLink.objects.bulk_update(
            to_update,
            [
                "http_status",
                "redirect_url",
                "status",
                "notes",
                "last_checked_at",
                "updated_at",
            ],
        )
