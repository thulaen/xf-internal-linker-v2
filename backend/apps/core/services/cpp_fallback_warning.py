"""Phase 4.14 — C++ Fallback Warning service.

Plain-English: when a C++ extension can't load (missing .so, ABI
mismatch, fresh-clone-without-build), the runtime silently falls back
to the Python reference implementation. Performance drops 5-50x, but
the operator has no visible signal that this happened — the system
just runs slow until someone notices.

This service watches the per-extension status and:

    * Emits a one-shot ``cpp_extension.fallback_started`` event into
      the Operations Feed when an extension transitions cpp→python.
    * Emits ``cpp_extension.fallback_recovered`` when it comes back.
    * Re-emits ``cpp_extension.fallback_persists`` every hour while
      the fallback is still active (so operators who joined late see
      the warning too).
    * Returns ``get_current_fallback_status()`` for the dashboard chip
      + ``format_dashboard_banner()`` for the at-a-glance banner.

Storage discipline: one ``AppSetting`` row per extension keyed
``cpp_fallback.<module>.last_state`` carrying a tiny JSON snapshot
(``{state, runtime_path, since_iso}``). NO new tables; rows are
update-not-append so storage doesn't pile up.

Citations:
    * The "watch + emit on transition" pattern is the operator-
      observability convention used by Linux PSI (Andrei 2018) and the
      Phoenix LiveView presence module.
    * Single-source-of-truth status detection: re-uses
      ``apps.diagnostics.health._native_module_runtime_status``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


# Per-extension AppSetting key prefix. One row per extension, single
# JSON value carrying state + transition timestamp. Update-not-append
# so storage never grows beyond `len(_NATIVE_RUNTIME_MODULES)` rows.
_KEY_PREFIX = "cpp_fallback."

# Re-emit "still on fallback" warning at most every 1 h while the
# fallback is active. The ops_feed emit() helper already dedupes
# repeats inside a 60-s window; this constant is the *minimum* spacing
# between fresh "still down" reminders the operator sees.
_PERSIST_REMINDER_INTERVAL_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class FallbackEvent:
    """One detected transition or persist event."""

    module: str
    label: str
    event_type: str  # "started" | "recovered" | "persists"
    runtime_path: str  # "cpp" | "python"
    severity: str  # "info" | "warning" | "high"
    plain_english: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class FallbackStatusSummary:
    """Operator-facing status snapshot for the dashboard chip."""

    total_extensions: int
    on_python_fallback: int
    on_cpp: int
    fallbacks: list[dict[str, Any]] = field(default_factory=list)


def check_and_emit_fallback_events() -> list[FallbackEvent]:
    """Detect C++→Python (and back) transitions; emit ops feed events.

    Plain-English: call this from a Celery beat task (every ~5 min).
    For every extension whose state changed since the last call, emit
    a one-shot ``cpp_extension.fallback_started`` (cpp→python) or
    ``cpp_extension.fallback_recovered`` (python→cpp) event into the
    Operations Feed. Persists "still down" reminder every 1 h.

    Returns the list of events emitted this call (for tests + the
    /diagnostics summary endpoint).
    """
    statuses = _read_native_runtime_status()
    if not statuses:
        return []

    events: list[FallbackEvent] = []
    for status in statuses:
        module = status.get("module", "")
        if not module:
            continue
        previous = _read_previous_state(module)
        current_path = str(status.get("runtime_path", "python"))
        label = str(status.get("label") or module)
        critical = bool(status.get("critical"))
        now = timezone.now()

        # First-ever observation of this extension. Just persist the
        # baseline; don't emit (operator doesn't need an event for
        # "system started up with cpp loaded" — that's the happy path).
        if previous is None:
            _persist_state(module, current_path, since=now)
            continue

        prev_path = previous.get("runtime_path", "python")
        prev_since = _parse_iso(previous.get("since_iso", ""))

        if current_path != prev_path:
            # Transition. Emit + persist new baseline.
            duration = (now - prev_since).total_seconds() if prev_since else 0.0
            event = _build_transition_event(
                module=module,
                label=label,
                from_path=prev_path,
                to_path=current_path,
                duration_seconds=duration,
                critical=critical,
            )
            events.append(event)
            _emit_event(event, status=status)
            _persist_state(module, current_path, since=now)
            continue

        # No transition. Decide whether to re-warn that fallback persists.
        # The persists event fires only when:
        #   1. the fallback is python (cpp doesn't need a "still healthy"
        #      reminder),
        #   2. the fallback has been active ≥ _PERSIST_REMINDER_INTERVAL_SECONDS
        #      (so a freshly-observed fallback gets one transition event,
        #      not an immediate "still down" follow-up), AND
        #   3. either we've never warned about this persist, or the
        #      previous warn was ≥ _PERSIST_REMINDER_INTERVAL_SECONDS ago.
        # Without rule (2), the very next call after baseline persisted
        # python state would emit one "persists" event per extension.
        if current_path == "python" and prev_since is not None:
            secs_since_started = (now - prev_since).total_seconds()
            if secs_since_started < _PERSIST_REMINDER_INTERVAL_SECONDS:
                continue
            last_warned = _parse_iso(previous.get("last_warned_iso", ""))
            secs_since_warn = (
                (now - last_warned).total_seconds()
                if last_warned
                else secs_since_started
            )
            if secs_since_warn >= _PERSIST_REMINDER_INTERVAL_SECONDS:
                event = _build_persists_event(
                    module=module,
                    label=label,
                    duration_seconds=secs_since_started,
                    critical=critical,
                )
                events.append(event)
                _emit_event(event, status=status)
                # Update last_warned_iso so we don't spam the operator.
                _persist_state(
                    module,
                    current_path,
                    since=prev_since,
                    last_warned=now,
                )

    return events


def get_current_fallback_status() -> FallbackStatusSummary:
    """Snapshot for the dashboard chip + /diagnostics card."""
    statuses = _read_native_runtime_status()
    on_fallback = 0
    on_cpp = 0
    fallbacks: list[dict[str, Any]] = []
    for status in statuses:
        if str(status.get("runtime_path")) == "cpp":
            on_cpp += 1
        else:
            on_fallback += 1
            module = str(status.get("module", ""))
            previous = _read_previous_state(module) or {}
            since = _parse_iso(previous.get("since_iso", ""))
            fallbacks.append(
                {
                    "module": module,
                    "label": status.get("label") or module,
                    "critical": bool(status.get("critical")),
                    "fallback_reason": status.get("fallback_reason", ""),
                    "since_iso": since.isoformat() if since else None,
                    "duration_seconds": (
                        (timezone.now() - since).total_seconds() if since else None
                    ),
                }
            )
    return FallbackStatusSummary(
        total_extensions=len(statuses),
        on_python_fallback=on_fallback,
        on_cpp=on_cpp,
        fallbacks=fallbacks,
    )


def format_dashboard_banner() -> str:
    """Return the at-a-glance banner string. Empty when all C++ loaded.

    Plain-English: the dashboard renders this banner at the top when
    ANY hot-path extension is on Python fallback. Operators can click
    through to /diagnostics for the per-extension breakdown.
    """
    snap = get_current_fallback_status()
    if snap.on_python_fallback == 0:
        return ""
    if snap.on_python_fallback == 1:
        which = snap.fallbacks[0]
        label = which.get("label") or which.get("module")
        return (
            f"Performance warning: {label} is on the Python fallback path. "
            "Performance may be 5-50x slower than normal. See /diagnostics."
        )
    return (
        f"Performance warning: {snap.on_python_fallback} of {snap.total_extensions} "
        "C++ extensions are on the Python fallback path. Performance may be "
        "significantly slower than normal. See /diagnostics for details."
    )


# ── Internal helpers ─────────────────────────────────────────────


def _read_native_runtime_status() -> list[dict[str, Any]]:
    """Re-export of the existing per-extension detector. Defensive."""
    try:
        from apps.diagnostics.health import _native_module_runtime_status

        return list(_native_module_runtime_status())
    except Exception:  # noqa: BLE001 — diagnostics import failure is non-fatal; treat as no extensions.
        logger.debug(
            "cpp_fallback_warning: native_module_runtime_status unavailable",
            exc_info=True,
        )
        return []


def _read_previous_state(module: str) -> dict[str, Any] | None:
    """Return the persisted JSON snapshot for *module* or None."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=f"{_KEY_PREFIX}{module}.last_state").first()
        if row is None or not row.value:
            return None
        return json.loads(row.value)
    except Exception:  # noqa: BLE001 — bad JSON or DB blip: treat as "no prior state".
        logger.debug(
            "cpp_fallback_warning: previous-state read failed for %s",
            module,
            exc_info=True,
        )
        return None


def _persist_state(
    module: str,
    runtime_path: str,
    *,
    since,
    last_warned=None,
) -> None:
    """Update the per-extension JSON snapshot. Best-effort."""
    try:
        from apps.core.models import AppSetting

        payload = {
            "runtime_path": runtime_path,
            "since_iso": since.isoformat() if since else "",
        }
        if last_warned is not None:
            payload["last_warned_iso"] = last_warned.isoformat()
        AppSetting.objects.update_or_create(
            key=f"{_KEY_PREFIX}{module}.last_state",
            defaults={"value": json.dumps(payload)},
        )
    except Exception:  # noqa: BLE001 — persistence is best-effort; transient blip just costs us one duplicate event next call.
        logger.debug(
            "cpp_fallback_warning: persist failed for %s",
            module,
            exc_info=True,
        )


def _build_transition_event(
    *,
    module: str,
    label: str,
    from_path: str,
    to_path: str,
    duration_seconds: float,
    critical: bool,
) -> FallbackEvent:
    if to_path == "python":
        # cpp→python = bad
        severity = "high" if critical else "warning"
        return FallbackEvent(
            module=module,
            label=label,
            event_type="started",
            runtime_path="python",
            severity=severity,
            plain_english=(
                f"{label} dropped to the Python fallback path. Performance "
                f"may be 5-50x slower. Rebuild the C++ extension via "
                f"'docker compose build backend' to recover."
            ),
            duration_seconds=duration_seconds,
        )
    # python→cpp = good
    duration_human = _format_duration(duration_seconds)
    return FallbackEvent(
        module=module,
        label=label,
        event_type="recovered",
        runtime_path="cpp",
        severity="info",
        plain_english=(
            f"{label} recovered to the C++ fast path after {duration_human} "
            f"on the Python fallback."
        ),
        duration_seconds=duration_seconds,
    )


def _build_persists_event(
    *,
    module: str,
    label: str,
    duration_seconds: float,
    critical: bool,
) -> FallbackEvent:
    severity = "high" if critical else "warning"
    duration_human = _format_duration(duration_seconds)
    return FallbackEvent(
        module=module,
        label=label,
        event_type="persists",
        runtime_path="python",
        severity=severity,
        plain_english=(
            f"{label} has been on the Python fallback path for {duration_human}. "
            f"Performance impact is ongoing. Rebuild via 'docker compose build "
            f"backend' to restore the fast path."
        ),
        duration_seconds=duration_seconds,
    )


def _emit_event(event: FallbackEvent, *, status: dict[str, Any]) -> None:
    """Best-effort emit through ops_feed.emit. Never raises."""
    try:
        from apps.ops_feed.services import emit

        emit(
            f"cpp_extension.fallback_{event.event_type}",
            event.plain_english,
            source="cpp_fallback_warning",
            severity=event.severity,
            related_entity_type="cpp_extension",
            related_entity_id=event.module,
            runtime_context={
                "module": event.module,
                "label": event.label,
                "runtime_path": event.runtime_path,
                "duration_seconds": round(event.duration_seconds, 1),
                "fallback_reason": status.get("fallback_reason", ""),
                "compiled": status.get("compiled", False),
                "importable": status.get("importable", False),
            },
        )
    except Exception:  # noqa: BLE001 — ops_feed already has its own failure suppression; double-guard for safety.
        logger.debug(
            "cpp_fallback_warning: emit failed for %s/%s",
            event.module,
            event.event_type,
            exc_info=True,
        )


def _parse_iso(value: str):
    """Parse an ISO-8601 timestamp; return None on failure."""
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: float) -> str:
    """Plain-English duration: '47s', '2m 14s', '1h 17m', '2d 3h'."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    if s < 86400:
        return f"{s // 3600}h {(s % 3600) // 60}m"
    return f"{s // 86400}d {(s % 86400) // 3600}h"
