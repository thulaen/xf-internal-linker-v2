"""Plain-English FR-016 browser bridge payloads."""

from __future__ import annotations

import json


def _js_bool(value: bool) -> str:
    return "true" if value else "false"


def _copyable_json(data: dict[str, object]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


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
    """Return a copy-ready browser snippet for live-site telemetry wiring."""

    config = {
        "eventSchema": event_schema,
        "impressionVisibleRatio": impression_visible_ratio,
        "impressionMinMs": impression_min_ms,
        "engagedMinSeconds": engaged_min_seconds,
        "sessionTtlMinutes": session_ttl_minutes,
        "ga4MeasurementId": ga4_measurement_id,
        "ga4Enabled": ga4_enabled,
        "matomoEnabled": matomo_enabled,
    }
    config_json = _copyable_json(config)
    return f"""<script>
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
+  document.querySelectorAll('a[data-xfil-suggestion-id]').forEach(wireLink);
+  emitDestinationView();
+  window.setTimeout(() => emitEngaged('focused_time'), config.engagedMinSeconds * 1000);
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
