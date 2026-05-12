from __future__ import annotations
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

from celery import shared_task
from django.db import DatabaseError, connection
from django.utils import timezone
from requests import RequestException
from urllib.error import URLError

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)

_MAX_BROKEN_LINK_SCAN_URLS = 10_000

def _publish_progress(job_id: str, state: str, progress: float, message: str, **extra: Any) -> None:
    from apps.pipeline.tasks import _publish_progress as base_publish
    base_publish(job_id, state, progress, message, **extra)

def _emit_job_alert(event_type: str, severity: str, title: str, message: str, **kwargs) -> None:
    from apps.pipeline.tasks import _emit_job_alert as base_alert
    base_alert(event_type, severity, title, message, **kwargs)

def _broken_link_allowed_domains() -> list[str]:
    from django.conf import settings
    allowed_domains: list[str] = []
    for raw_url in [getattr(settings, "XENFORO_BASE_URL", ""), getattr(settings, "WORDPRESS_BASE_URL", "")]:
        host = urlparse(raw_url).netloc.strip().lower()
        if host and host not in allowed_domains:
            allowed_domains.append(host)
    return allowed_domains

@shared_task(name="pipeline.scan_broken_links", time_limit=3600, soft_time_limit=3540)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def scan_broken_links(job_id: str | None = None) -> dict:
    """FR-005 — identify and flag broken outbound internal links."""
    if not connection.in_atomic_block:
        connection.close()
    
    from apps.pipeline.services.broken_links import (
        collect_urls_to_scan,
        build_existing_records_map,
        scan_via_async_http,
        persist_scan_results,
    )

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Collecting links for health check...")
    
    allowed_domains = _broken_link_allowed_domains()
    urls_to_scan, total_urls, hit_scan_cap = collect_urls_to_scan(
        allowed_domains=allowed_domains,
        max_urls=_MAX_BROKEN_LINK_SCAN_URLS,
    )

    if not urls_to_scan:
        _publish_progress(job_id, "completed", 1.0, "No internal links found to scan.")
        return {"scanned": 0, "job_id": job_id}

    checked_at = timezone.now()
    scan_items = list(urls_to_scan.values())
    existing_records = build_existing_records_map(urls_to_scan)
    to_create: list = []
    to_update: list = []
    
    flagged_urls, fixed_urls, probe_backend = scan_via_async_http(
        scan_items,
        job_id=job_id,
        total_urls=total_urls,
        existing_records=existing_records,
        to_create=to_create,
        to_update=to_update,
        checked_at=checked_at,
        hit_scan_cap=hit_scan_cap,
    )
    persist_scan_results(to_create, to_update)
    
    _publish_broken_link_scan_completion(job_id, total_urls, flagged_urls, fixed_urls, hit_scan_cap, probe_backend)
    return {"scanned": total_urls, "flagged": flagged_urls, "job_id": job_id}

def _publish_broken_link_scan_completion(job_id, total_urls, flagged_urls, fixed_urls, hit_scan_cap, probe_backend):
    msg = f"Broken link scan complete. {flagged_urls} flagged, {fixed_urls} resolved."
    if hit_scan_cap:
        msg += f" Stopped at {_MAX_BROKEN_LINK_SCAN_URLS:,} cap."
    _publish_progress(job_id, "completed", 1.0, msg, scanned_urls=total_urls, flagged_urls=flagged_urls, fixed_urls=fixed_urls, hit_scan_cap=hit_scan_cap, probe_backend=probe_backend)

@shared_task(bind=True, name="pipeline.verify_suggestions", time_limit=3600)
@HelperConstraint(cpu_intensive=False, gpu_required=False, storage_writes_to="postgres_main", ram_peak_mb=256, expected_seconds_p50=300)
def verify_suggestions(self, suggestion_ids: list[str] | None = None) -> dict:
    """Check whether applied suggestions are still live via XenForo API."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.suggestions.models import Suggestion
    from apps.sync.services.xenforo_api import XenForoAPIClient

    job_id = str(uuid.uuid4())
    _publish_progress(job_id, "running", 0.0, "Starting verification...")
    suggestions = Suggestion.objects.filter(status="applied")
    if suggestion_ids:
        suggestions = suggestions.filter(pk__in=suggestion_ids)
    total = suggestions.count()
    if total == 0:
        _publish_progress(job_id, "completed", 1.0, "No applied suggestions to verify.")
        return {"verified": 0, "stale": 0, "job_id": job_id}
    
    try:
        verified, stale = _run_suggestion_verifications(XenForoAPIClient(), suggestions, total, job_id)
        _publish_progress(job_id, "completed", 1.0, f"Verification complete. {verified} verified, {stale} stale.")
        return {"verified": verified, "stale": stale, "job_id": job_id}
    except Exception as exc:
        logger.exception("Verification %s failed", job_id)
        _publish_progress(job_id, "failed", 0.0, f"Verification failed: {exc}", error=str(exc))
        raise

def _run_suggestion_verifications(client, suggestions, total: int, job_id: str) -> tuple[int, int]:
    verified = stale = 0
    for index, suggestion in enumerate(suggestions):
        _publish_progress(job_id, "running", index / total, f"Checking suggestion {str(suggestion.suggestion_id)[:8]}...")
        result = _verify_one_suggestion(client, suggestion)
        if result == "verified": verified += 1
        elif result == "stale": stale += 1
    return verified, stale

def _verify_one_suggestion(client, suggestion) -> str:
    from django.utils import timezone
    host_content = suggestion.host
    if not host_content or not host_content.xf_post_id:
        return "skip"
    try:
        raw_bbcode = client.get_post(host_content.xf_post_id).get("post", {}).get("message", "")
    except (TimeoutError, RequestException, URLError) as exc:
        logger.error("Failed to fetch host post for suggestion %s: %s", suggestion.suggestion_id, exc)
        return "skip"
    
    destination_url = suggestion.destination.url
    if f"[URL='{destination_url}']" in raw_bbcode or f"[URL=\"{destination_url}\"]" in raw_bbcode or destination_url in raw_bbcode:
        suggestion.status = "applied"
        suggestion.verified_at = timezone.now()
        suggestion.save(update_fields=["status", "verified_at", "updated_at"])
        return "verified"
    
    suggestion.status = "stale"
    suggestion.stale_reason = "Link not found in host post body"
    suggestion.save(update_fields=["status", "stale_reason", "updated_at"])
    return "stale"
