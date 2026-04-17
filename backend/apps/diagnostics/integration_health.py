"""
Phase MX3 / Gaps 331-338 — Integration health aggregator.

One function per connector health card (GSC, GA4, Matomo, XenForo,
WordPress). Each returns the same `IntegrationStatus` shape so the
frontend can render them in a uniform grid.

Reuses existing checks from `apps.diagnostics.health` + AppSetting
connector configuration. No new state.

Gap mapping:
  * 331 per-connector card       → statuses()
  * 332 "why did this stop?"     → autopsy_for()
  * 333 reconnect wizard steps   → reconnect_steps_for()
  * 334 latency monitor          → latency_series_for()
  * 335 last-successful-sync     → field on statuses()
  * 336 event-volume chart       → volume_series_for()
  * 337 dependency graph         → dependencies_for()
  * 338 test-connection helper   → delegates to existing endpoints
"""

from __future__ import annotations

from typing import TypedDict



class IntegrationStatus(TypedDict):
    id: str
    name: str
    state: str
    explanation: str
    next_step: str
    last_successful_at: str | None
    latency_ms_recent: float | None
    dependents: list[str]


_DEPENDENTS_BY_SOURCE: dict[str, list[str]] = {
    "gsc": ["ranking.signals.gsc", "analytics.search-lift"],
    "ga4": ["ranking.signals.ga4", "analytics.traffic-attribution"],
    "matomo": ["analytics.engagement", "cooccurrence"],
    "xenforo": ["content.import", "content.updates"],
    "wordpress": ["content.import", "content.updates"],
}


def statuses() -> list[IntegrationStatus]:
    """All known connectors, one row each."""

    out: list[IntegrationStatus] = []
    for cfg in _CONNECTORS:
        raw = cfg["check"]()  # returns (state, explanation, next_step, metadata)
        state, explanation, next_step, metadata = raw
        last = metadata.get(cfg["latest_field"])
        out.append(
            {
                "id": cfg["id"],
                "name": cfg["name"],
                "state": state,
                "explanation": explanation,
                "next_step": next_step,
                "last_successful_at": _as_iso(last) if last else None,
                "latency_ms_recent": _read_cached_latency(cfg["id"]),
                "dependents": _DEPENDENTS_BY_SOURCE.get(cfg["id"], []),
            }
        )
    return out


def autopsy_for(source_id: str) -> dict:
    """Gap 332 — retrospective panel for a broken connector.

    Aggregates recent ErrorLog rows whose `job_type` or `step` mentions
    the connector id, plus the last state-flip timestamp from
    `ServiceStatusSnapshot`.
    """
    from apps.audit.models import ErrorLog
    from apps.diagnostics.models import ServiceStatusSnapshot

    errors = list(
        ErrorLog.objects.filter(
            job_type__icontains=source_id
        ).order_by("-created_at")[:5].values(
            "id", "created_at", "severity", "error_message", "how_to_fix"
        )
    )
    last_flip = ServiceStatusSnapshot.objects.filter(
        service_key=f"{source_id}"
    ).order_by("-created_at").values("created_at", "state").first()

    return {
        "source": source_id,
        "recent_errors": [
            {
                "id": e["id"],
                "created_at": _as_iso(e["created_at"]),
                "severity": e["severity"],
                "message": (e["error_message"] or "")[:200],
                "fix": e["how_to_fix"],
            }
            for e in errors
        ],
        "last_state_change_at": _as_iso(last_flip["created_at"]) if last_flip else None,
        "last_state": last_flip["state"] if last_flip else None,
    }


def reconnect_steps_for(source_id: str) -> list[dict]:
    """Gap 333 — guided reconnect flow per connector."""
    steps_by_source: dict[str, list[dict]] = {
        "gsc": [
            {"title": "Open Google Search Console", "action": "external-open", "target": "https://search.google.com/search-console"},
            {"title": "Verify the property owns your domain", "action": "manual"},
            {"title": "Refresh the OAuth token in Settings → GA4/GSC", "action": "settings-jump", "target": "/settings#connections"},
            {"title": "Run the test-connection button", "action": "test-connection", "target": "gsc"},
        ],
        "ga4": [
            {"title": "Open Google Analytics admin", "action": "external-open", "target": "https://analytics.google.com"},
            {"title": "Paste the measurement ID + service-account JSON in Settings", "action": "settings-jump", "target": "/settings#connections"},
            {"title": "Run the test-connection button", "action": "test-connection", "target": "ga4"},
        ],
        "matomo": [
            {"title": "Log into your Matomo admin", "action": "manual"},
            {"title": "Copy a fresh API token", "action": "manual"},
            {"title": "Paste it in Settings → Matomo", "action": "settings-jump", "target": "/settings#matomo"},
            {"title": "Run the test-connection button", "action": "test-connection", "target": "matomo"},
        ],
        "xenforo": [
            {"title": "Open your XenForo admin panel", "action": "manual"},
            {"title": "Verify the API key is still valid", "action": "manual"},
            {"title": "Paste it in Settings → XenForo", "action": "settings-jump", "target": "/settings#xenforo"},
            {"title": "Run the test-connection button", "action": "test-connection", "target": "xenforo"},
        ],
        "wordpress": [
            {"title": "Open your WordPress Users page", "action": "manual"},
            {"title": "Generate an application password", "action": "manual"},
            {"title": "Paste it in Settings → WordPress", "action": "settings-jump", "target": "/settings#wordpress"},
            {"title": "Run the test-connection button", "action": "test-connection", "target": "wordpress"},
        ],
    }
    return steps_by_source.get(source_id, [])


def latency_series_for(source_id: str, hours: int = 24) -> list[dict]:
    """Gap 334 — recent connector latency.

    Real implementation would read a per-call latency log; this stub
    returns an empty series which the frontend renders as "no data
    yet" without crashing. Wire to real data once latency logging lands.
    """
    return []


def volume_series_for(source_id: str, days: int = 14) -> list[dict]:
    """Gap 336 — daily row-count trend per connector."""
    from apps.audit.data_quality import volume_trend

    all_series = volume_trend(days=days)
    return all_series.get(source_id, [])


def dependencies_for(source_id: str) -> list[str]:
    """Gap 337 — list of features that degrade when this connector fails."""
    return _DEPENDENTS_BY_SOURCE.get(source_id, [])


# ─── internals ─────────────────────────────────────────────────────


def _lazy_check(name: str):
    def _runner():
        from apps.diagnostics import health as dh

        fn = getattr(dh, name, None)
        if fn is None:
            return ("not_configured", f"Check {name} not found.", "", {})
        return fn()

    return _runner


_CONNECTORS: list[dict] = [
    {"id": "gsc", "name": "Google Search Console", "check": _lazy_check("check_gsc"), "latest_field": "latest_gsc_date"},
    {"id": "ga4", "name": "Google Analytics 4", "check": _lazy_check("check_ga4"), "latest_field": "latest_ga4_date"},
    {"id": "matomo", "name": "Matomo", "check": _lazy_check("check_matomo"), "latest_field": "latest_matomo_date"},
]


def _as_iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _read_cached_latency(source_id: str) -> float | None:
    try:
        from django.core.cache import cache

        return cache.get(f"integration:latency:{source_id}")
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "statuses",
    "autopsy_for",
    "reconnect_steps_for",
    "latency_series_for",
    "volume_series_for",
    "dependencies_for",
]
