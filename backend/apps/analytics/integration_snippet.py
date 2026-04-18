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

#: Time after view beyond which a session no longer counts as a quick-exit.
QUICK_EXIT_THRESHOLD_MS = 5000

#: Dwell checkpoint delays fired after view if the user is still on the page.
DWELL_30S_THRESHOLD_MS = 30000
DWELL_60S_THRESHOLD_MS = 60000


def _js_bool(value: bool) -> str:
    return "true" if value else "false"


def _copyable_json(data: dict[str, object]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


#: Full JS body of the browser-bridge snippet. Kept at module scope so the
#: per-function 80-line cap applies only to the small Python wrappers.
#: Python-side braces must be doubled (``{{``, ``}}``) — we format the
#: ``{config_json}`` slot at call time via :func:`_build_bridge_js`.
_BRIDGE_JS_TEMPLATE = """<script>
+(() => {{
+  const config = {config_json};
+  const storageKey = 'xfil_fr016_attribution_v1';
+  const impressionSeen = new Set();
+  const clickSeen = new Set();
+  const viewSeen = new Set();
+  let engagedSent = false;
+
+  function readAttrs(link) {{
+    const data = link?.dataset ?? {{}};
+    if (!data.xfilSuggestionId || !data.xfilDestinationId) {{
+      return null;
+    }}
+    return {{
+      xfil_schema: data.xfilSchema || config.eventSchema,
+      suggestion_id: data.xfilSuggestionId,
+      pipeline_run_id: data.xfilPipelineRunId || '',
+      algorithm_key: data.xfilAlgorithmKey || '',
+      algorithm_version_date: data.xfilAlgorithmVersionDate || '',
+      algorithm_version_slug: data.xfilAlgorithmVersionSlug || '',
+      destination_id: data.xfilDestinationId || '',
+      destination_type: data.xfilDestinationType || '',
+      host_id: data.xfilHostId || '',
+      host_type: data.xfilHostType || '',
+      source_label: data.xfilSourceLabel || '',
+      same_silo: data.xfilSameSilo || '0',
+      link_position_bucket: data.xfilLinkPositionBucket || 'unknown',
+      anchor_hash: data.xfilAnchorHash || '',
+      anchor_length: Number(data.xfilAnchorLength || 0),
+      destination_path: new URL(link.href, window.location.origin).pathname,
+    }};
+  }}
+
+  function emit(eventName, params) {{
+    if (config.ga4Enabled && typeof window.gtag === 'function') {{
+      window.gtag('event', eventName, params);
+    }}
+    if (config.matomoEnabled && Array.isArray(window._paq)) {{
+      window._paq.push(['trackEvent', 'XF Internal Linker', eventName, params.suggestion_id || 'unknown', 1]);
+    }}
+  }}
+
+  function saveAttribution(payload) {{
+    const stored = {{
+      ...payload,
+      saved_at: Date.now(),
+      expires_at: Date.now() + config.sessionTtlMinutes * 60 * 1000,
+    }};
+    sessionStorage.setItem(storageKey, JSON.stringify(stored));
+  }}
+
+  function readAttribution() {{
+    try {{
+      const raw = sessionStorage.getItem(storageKey);
+      if (!raw) return null;
+      const parsed = JSON.parse(raw);
+      if (!parsed || parsed.expires_at < Date.now()) {{
+        sessionStorage.removeItem(storageKey);
+        return null;
+      }}
+      return parsed;
+    }} catch (_error) {{
+      sessionStorage.removeItem(storageKey);
+      return null;
+    }}
+  }}
+
+  function wireLink(link) {{
+    const payload = readAttrs(link);
+    if (!payload) return;
+
+    const suggestionKey = payload.suggestion_id;
+    const observer = new IntersectionObserver((entries) => {{
+      for (const entry of entries) {{
+        if (!entry.isIntersecting || entry.intersectionRatio < config.impressionVisibleRatio) {{
+          continue;
+        }}
+        window.setTimeout(() => {{
+          if (impressionSeen.has(suggestionKey)) return;
+          impressionSeen.add(suggestionKey);
+          emit('suggestion_link_impression', payload);
+        }}, config.impressionMinMs);
+      }}
+    }}, {{ threshold: [config.impressionVisibleRatio] }});
+    observer.observe(link);
+
+    link.addEventListener('click', () => {{
+      if (clickSeen.has(suggestionKey)) return;
+      clickSeen.add(suggestionKey);
+      emit('suggestion_link_click', payload);
+      saveAttribution(payload);
+    }});
+  }}
+
+  function emitDestinationView() {{
+    const payload = readAttribution();
+    if (!payload) return;
+    if (payload.destination_path !== window.location.pathname) return;
+    if (viewSeen.has(payload.suggestion_id)) return;
+    viewSeen.add(payload.suggestion_id);
+    emit('suggestion_destination_view', payload);
+  }}
+
+  function emitEngaged(reason) {{
+    const payload = readAttribution();
+    if (!payload || engagedSent) return;
+    if (payload.destination_path !== window.location.pathname) return;
+    engagedSent = true;
+    emit('suggestion_destination_engaged', {{ ...payload, engaged_reason: reason }});
+  }}
+
+  // Phase 2 engagement: quick-exit detection + dwell checkpoints.
+  // Source: Kim, Hassan, White, Zitouni (WSDM 2014).
+  let destinationViewedAt = 0;
+  let quickExitSent = false;
+  let dwell30Sent = false;
+  let dwell60Sent = false;
+
+  function markDestinationViewed() {{
+    const payload = readAttribution();
+    if (!payload) return;
+    if (payload.destination_path !== window.location.pathname) return;
+    if (destinationViewedAt > 0) return;
+    destinationViewedAt = Date.now();
+  }}
+
+  function maybeEmitQuickExit() {{
+    if (quickExitSent || engagedSent || destinationViewedAt === 0) return;
+    const elapsed = Date.now() - destinationViewedAt;
+    if (elapsed >= config.quickExitThresholdMs) return;
+    const payload = readAttribution();
+    if (!payload) return;
+    quickExitSent = true;
+    emit('suggestion_destination_quick_exit', {{
+      ...payload,
+      dwell_ms_before_exit: elapsed,
+    }});
+  }}
+
+  function emitDwellCheckpoint(eventName, sentFlag) {{
+    if (sentFlag) return true;
+    const payload = readAttribution();
+    if (!payload) return true;
+    if (payload.destination_path !== window.location.pathname) return true;
+    emit(eventName, payload);
+    return true;
+  }}
+
+  document.querySelectorAll('a[data-xfil-suggestion-id]').forEach(wireLink);
+  emitDestinationView();
+  markDestinationViewed();
+  window.setTimeout(() => emitEngaged('focused_time'), config.engagedMinSeconds * 1000);
+  window.setTimeout(() => {{
+    dwell30Sent = emitDwellCheckpoint('suggestion_destination_dwell_30s', dwell30Sent);
+  }}, config.dwell30sThresholdMs);
+  window.setTimeout(() => {{
+    dwell60Sent = emitDwellCheckpoint('suggestion_destination_dwell_60s', dwell60Sent);
+  }}, config.dwell60sThresholdMs);
+  document.addEventListener('visibilitychange', () => {{
+    if (document.visibilityState === 'hidden') maybeEmitQuickExit();
+  }});
+  window.addEventListener('scroll', () => {{
+    const doc = document.documentElement;
+    const maxScroll = doc.scrollHeight - window.innerHeight;
+    if (maxScroll <= 0) return;
+    const ratio = window.scrollY / maxScroll;
+    if (ratio >= 0.5) {{
+      emitEngaged('scroll_depth');
+    }}
+  }}, {{ passive: true }});
+}})();
+</script>"""


def _build_bridge_js(config_json: str) -> str:
    """Return the JS body with ``config_json`` formatted into the template.

    The template itself lives at module scope in ``_BRIDGE_JS_TEMPLATE`` so
    the project-wide 80-line per-function cap is not blown by what is
    essentially one long string constant.
    """
    return _BRIDGE_JS_TEMPLATE.format(config_json=config_json)


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
        "sessionTtlMinutes": session_ttl_minutes,
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
        impression_min_ms=int(ga4_settings.get("impression_min_ms") or 1000),
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
