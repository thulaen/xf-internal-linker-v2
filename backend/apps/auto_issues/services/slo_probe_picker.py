"""Synthetic SLO probes → AutoIssue picker.

Closes Gap #6 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Catches the
"external API throttled or degraded" failure mode that surfaces as
sync-task warnings but never as a user-facing crash.

Each target is a (label, url, expected_status, max_latency_ms) tuple.
The picker fires a HEAD/GET (per probe), records latency, and emits an
AutoIssue when:
  - status mismatch (expected 200, got 5xx/timeout)
  - latency exceeds threshold

Cross-source dedup via `services.dedup.upsert_dedup` so a flapping
endpoint doesn't generate one row per probe — same canonical fingerprint
per target name.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class _Probe:
    name: str
    url: str
    method: str            # "GET" or "HEAD"
    expected_status: tuple[int, ...]
    max_latency_ms: float


# Probe targets — all internal/local, none reach the public internet
# (so we don't risk leaking project identity to a third party). External
# API health (GA4, Matomo) is best-monitored by their own status pages
# + the existing sync-error path; adding a synthetic poll there would
# exceed our quota under no fault of our own.
_PROBES: tuple[_Probe, ...] = (
    _Probe("backend-health", "http://backend:8000/api/system/health/",
           "GET", (200,), 15000.0),
    _Probe("glitchtip-root", "http://glitchtip:8000/",
           "GET", (200, 301, 302), 10000.0),
    _Probe("pyroscope-ready", "http://pyroscope:4040/ready",
           "GET", (200, 503), 8000.0),
    _Probe("postgres-exporter", "http://postgres-exporter:9187/metrics",
           "GET", (200,), 8000.0),
    _Probe("otel-metrics", "http://otel-collector:8889/metrics",
           "GET", (200,), 8000.0),
)


def _run_one_probe(p: _Probe) -> tuple[int | None, float | None, str | None]:
    """Returns (status_code, latency_ms, error_msg). Two of three Nones on success."""
    start = time.monotonic()
    try:
        response = requests.request(
            p.method, p.url, timeout=_REQUEST_TIMEOUT_S, allow_redirects=False
        )
    except requests.RequestException as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        return None, latency_ms, str(exc)[:200]
    latency_ms = (time.monotonic() - start) * 1000.0
    return response.status_code, latency_ms, None


def _classify(p: _Probe, status: int | None, latency: float | None,
              error: str | None) -> tuple[str | None, str]:
    """Return (severity, reason). severity=None means probe is healthy."""
    if error is not None:
        return AutoIssue.SEVERITY_HIGH, f"connection error: {error}"
    if status not in p.expected_status:
        return (
            AutoIssue.SEVERITY_HIGH,
            f"status {status} (expected {p.expected_status})",
        )
    if latency is not None and latency > p.max_latency_ms:
        return (
            AutoIssue.SEVERITY_MEDIUM,
            f"latency {latency:.0f} ms (threshold {p.max_latency_ms:.0f} ms)",
        )
    return None, "ok"


def _upsert_probe_issue(p: _Probe, severity: str, reason: str) -> str:
    title = f"SLO breach: {p.name} — {reason}"
    description = (
        f"Synthetic probe `{p.name}` ({p.method} {p.url}) reported "
        f"{reason}. Expected status {p.expected_status}, max latency "
        f"{p.max_latency_ms:.0f} ms. Probes run every 15 min during the "
        f"active-laptop window (11:00–23:00 UTC). If the issue is "
        f"intermittent, check `auto_issues.source_observations` for the "
        f"trend; a single failure may be a transient blip, but repeated "
        f"failures in `last_seen` indicate a real degradation."
    )
    canonical = canonical_fingerprint(f"slo::{p.name}", "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"slo-{p.name}",
        fingerprint=f"slo-{p.name}",
        title=title,
        description=description,
        affected_files=[],
        severity=severity,
        priority_score=0.7 if severity == AutoIssue.SEVERITY_HIGH else 0.4,
        occurrence_count=1,
    )
    return outcome


def pick_slo_probes() -> dict:
    """Run every probe, surface failures into auto_issues."""
    counts = {"created": 0, "merged": 0, "updated": 0, "ok": 0}
    for p in _PROBES:
        status, latency, error = _run_one_probe(p)
        severity, reason = _classify(p, status, latency, error)
        if severity is None:
            counts["ok"] += 1
            continue
        outcome = _upsert_probe_issue(p, severity, reason)
        counts[outcome] = counts.get(outcome, 0) + 1
    logger.info(
        "[auto_issues.slo_probe_picker] probes=%d ok=%d created=%d merged=%d updated=%d",
        len(_PROBES), counts["ok"], counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "probes": len(_PROBES),
        "promoted": counts["created"] + counts["merged"] + counts["updated"],
        **counts,
    }
