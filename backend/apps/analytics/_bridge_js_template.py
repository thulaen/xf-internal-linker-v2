"""Module-scope JS template for the FR-016 browser bridge.

Kept in its own file so that `integration_snippet.py` doesn't carry a long
string constant between its Python helpers. The project-wide function-length
linter (80-line cap, see AGENTS.md §CI-and-Testing / rule 4) counts lines
between top-level ``def`` statements, and a long constant between two short
helpers would cause one of them to blow the cap even though no actual
function body is that long.

The template uses ``str.format`` slots (``{config_json}``), so every JS
literal brace is doubled (``{{``, ``}}``).
"""

from __future__ import annotations

BRIDGE_JS_TEMPLATE = """<script>
+(() => {{
+  const config = {config_json};
+  const storageKey = 'xfil_fr016_attribution_v1';
+  const xfilVisitStorageKey = 'xfil_first_party_visit_id_v1';
+  const impressionSeen = new Set();
+  const clickSeen = new Set();
+  const viewSeen = new Set();
+  let engagedSent = false;
+
+  function randomVisitId() {{
+    if (window.crypto && typeof window.crypto.randomUUID === 'function') {{
+      return window.crypto.randomUUID();
+    }}
+    return `xfil-${{Date.now()}}-${{Math.random().toString(16).slice(2)}}`;
+  }}
+
+  function currentVisitId() {{
+    let visitId = sessionStorage.getItem(xfilVisitStorageKey);
+    if (!visitId) {{
+      visitId = randomVisitId();
+      sessionStorage.setItem(xfilVisitStorageKey, visitId);
+    }}
+    return visitId;
+  }}
+
+  const xfilVisitId = currentVisitId();
+
+  function withVisitId(params) {{
+    return {{ ...params, xfil_visit_id: xfilVisitId }};
+  }}
+
+  function configureTrackerIdentity() {{
+    if (config.ga4Enabled && typeof window.gtag === 'function') {{
+      window.gtag('set', 'user_properties', {{ xfil_visit_id: xfilVisitId }});
+      window.gtag('event', 'page_view', {{
+        page_location: window.location.href,
+        page_referrer: document.referrer || '',
+        xfil_visit_id: xfilVisitId,
+        xfil_identity_only: '1',
+      }});
+    }}
+    if (config.matomoEnabled && Array.isArray(window._paq)) {{
+      window._paq.push(['setUserId', xfilVisitId]);
+      window._paq.push(['setCustomVariable', 1, 'xfil_visit_id', xfilVisitId, 'visit']);
+    }}
+  }}
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
+    const enriched = withVisitId(params);
+    if (config.ga4Enabled && typeof window.gtag === 'function') {{
+      window.gtag('event', eventName, enriched);
+    }}
+    if (config.matomoEnabled && Array.isArray(window._paq)) {{
+      window._paq.push(['trackEvent', 'XF Internal Linker', eventName, enriched.suggestion_id || 'unknown', 1]);
+    }}
+  }}
+
+  function saveAttribution(payload) {{
+    const stored = {{
+      ...payload,
+      saved_at: Date.now(),
+      expires_at: Date.now() + config.sessionTtlMs,
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
+  configureTrackerIdentity();
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
