"""Plain-English FR-016 browser bridge payloads.

Phase 2 richer engagement signals. Original FR-016 events
(`suggestion_link_impression`, `_click`, `_destination_view`, `_engaged`,
`_conversion`) stay unchanged. Three new events extend the destination-side
contract without breaking existing GA4 / Matomo consumers:

- ``suggestion_destination_quick_exit`` — fires on ``visibilitychange`` to
  'hidden' within 5s of ``suggestion_destination_view`` when the session has
  not been marked engaged. Count per day = quick_exit_sessions rollup column.
- ``suggestion_destination_dwell_30s`` — fires 30s after view.
- ``suggestion_destination_dwell_60s`` — fires 60s after view.

Combined with the existing 10s `engaged` threshold, this produces a three-tier
dwell distribution (10s+ engaged, 30s+ dwell, 60s+ dwell) — aligned with Kim,
Hassan, White & Zitouni 2014 "Modeling dwell time to predict click-level
satisfaction" (WSDM). All three events are simple event counts — they slot
into GA4 and Matomo's standard event-count aggregation without requiring
custom numeric metrics or operator config changes.
"""

from __future__ import annotations

import json

from ._bridge_js_template import BRIDGE_JS_TEMPLATE

#: Time after view beyond which a session no longer counts as a quick-exit.
QUICK_EXIT_THRESHOLD_MS = 5_000  # ms

#: Dwell checkpoint delays fired after view if the user is still on the page.
DWELL_30S_THRESHOLD_MS = 30_000  # ms
DWELL_60S_THRESHOLD_MS = 60_000  # ms

#: Fallback impression visibility threshold when GA4 settings do not set one.
DEFAULT_IMPRESSION_MIN_MS = 1_000  # ms

#: Minutes-to-milliseconds conversion factor — one minute in milliseconds.
_MS_PER_MINUTE = 60_000  # ms


def _js_bool(value: bool) -> str:
    return "true" if value else "false"


def _copyable_json(data: dict[str, object]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _build_bridge_js(config_json: str) -> str:
    """Return the JS body with ``config_json`` formatted into the template.

    The template itself lives in ``_bridge_js_template.py`` so the
    project-wide per-function 80-line cap is not blown by what is essentially
    one long string constant.
    """
    return BRIDGE_JS_TEMPLATE.format(config_json=config_json)


def build_browser_bridge_snippet(
    *,
    event_schema: str,
    impression_visible_ratio: float,
    impression_min_ms: int,
    engaged_min_seconds: int,
    ga4_measurement_id: str,
    ga4_enabled: bool,
    matomo_enabled: bool,
    session_ttl_minutes: int = 30,
) -> str:
    """Return a copy-ready browser snippet for live-site telemetry wiring.

    Builds the config dict and delegates the long JS body to
    :func:`_build_bridge_js` — keeps this function under the 80-line cap.
    """
    config = {
        "eventSchema": event_schema,
        "impressionVisibleRatio": impression_visible_ratio,
        "impressionMinMs": impression_min_ms,
        "engagedMinSeconds": engaged_min_seconds,
        # Pre-computed as milliseconds so the JS bridge avoids a raw
        # minute->ms multiplication inside its string literal.
        "sessionTtlMs": session_ttl_minutes * _MS_PER_MINUTE,
        "ga4MeasurementId": ga4_measurement_id,
        "ga4Enabled": ga4_enabled,
        "matomoEnabled": matomo_enabled,
        # Phase 2 engagement signals — see module docstring.
        "quickExitThresholdMs": QUICK_EXIT_THRESHOLD_MS,
        "dwell30sThresholdMs": DWELL_30S_THRESHOLD_MS,
        "dwell60sThresholdMs": DWELL_60S_THRESHOLD_MS,
    }
    return _build_bridge_js(_copyable_json(config))


def build_integration_payload(
    *, ga4_settings: dict, matomo_settings: dict
) -> dict[str, object]:
    """Return read-only setup status plus a copy-ready browser bridge snippet."""

    event_schema = (
        str(ga4_settings.get("event_schema") or "fr016_v1").strip() or "fr016_v1"
    )
    measurement_id = str(ga4_settings.get("measurement_id") or "").strip().upper()
    ga4_enabled = bool(ga4_settings.get("behavior_enabled")) and bool(measurement_id)
    matomo_enabled = bool(matomo_settings.get("enabled")) and bool(
        matomo_settings.get("url")
    )
    ready = ga4_enabled or matomo_enabled

    if ready:
        status = "ready"
        message = "Copy this browser snippet into XenForo or WordPress so instrumented links can send impressions, clicks, and destination visits."
    else:
        status = "needs_settings"
        message = "Turn on GA4 browser events or Matomo collection first, then copy the browser snippet into the live site."

    snippet = build_browser_bridge_snippet(
        event_schema=event_schema,
        impression_visible_ratio=float(
            ga4_settings.get("impression_visible_ratio") or 0.5
        ),
        impression_min_ms=int(
            ga4_settings.get("impression_min_ms") or DEFAULT_IMPRESSION_MIN_MS
        ),
        engaged_min_seconds=int(ga4_settings.get("engaged_min_seconds") or 10),
        ga4_measurement_id=measurement_id,
        ga4_enabled=ga4_enabled,
        matomo_enabled=matomo_enabled,
    )
    return {
        "status": status,
        "message": message,
        "event_schema": event_schema,
        "ga4_browser_ready": ga4_enabled,
        "matomo_browser_ready": matomo_enabled,
        "session_ttl_minutes": 30,
        "install_steps": [
            "Paste this script into the shared footer or template area on the live XenForo and WordPress sites.",
            "Render approved links with the data-xfil-* attributes shown in the review dialog.",
            "Open a page with an instrumented link, click it once, and confirm the events appear in GA4 or Matomo.",
        ],
        "browser_snippet": snippet,
    }
