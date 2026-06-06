"""
Runtime, system-metrics, and safe-mode view layer extracted from
``apps/core/views.py``.

Why this file exists
--------------------
``apps/core/views.py`` was the historical home of every view in the
core app and grew well past the 1500-line cap that ``CLAUDE.md`` (Code
Quality Mandate) targets. The first slice (2026-05-10, commit
c315c40d) moved the per-feature settings views into
``views_settings.py``. This is the **second** slice — the runtime mode
+ master-pause + maintenance-mode + system-metrics + runtime-config +
safe-mode-boot view classes plus the small helpers they rely on
exclusively.

Behaviour preserved exactly
---------------------------
This is a pure mechanical refactor. No request shape, validation rule,
or response payload changed. The original ``apps.core.views`` module
re-exports every class and helper defined in this file at the end of
``views.py`` so existing importers (``apps/core/urls.py``,
``apps/core/tests_dashboard_helpers.py``, etc.) keep working unchanged
via the ``from apps.core.views import …`` path they already use.

Helpers that remain in views.py (e.g. the ``_today_view_*``,
``_dashboard_*``, ``get_silo_settings``, etc.) are reused by other
view families that did not move out, so they stay where they are.
This file only owns the helpers used solely by the runtime/system
view classes — and the few module-level constants (the runtime keys
tuple, performance-mode + expiry choice tuples, and byte conversion
constants) that are exclusive to this layer.
"""

from __future__ import annotations

import json
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


_RUNTIME_SETTINGS_KEYS = (
    "system.runtime_mode",
    "system.performance_mode",
    "system.performance_mode_expiry",
    "system.performance_mode_expires_at",
    "system.master_pause",
)


def _runtime_settings_snapshot() -> dict[str, object]:
    """Return the live runtime / performance / master-pause snapshot.

    Defensive: any failure (cold-start AppSetting unavailable, embeddings
    module not importable, etc.) returns the safe defaults so the
    settings page still renders. Single bulk query (one round trip) is
    used instead of the original inline 5×.first() pattern (DRY win).
    """
    from apps.core.models import AppSetting
    from apps.core.performance_mode import get_requested_performance_mode

    defaults: dict[str, object] = {
        "runtime_mode": "cpu",
        "performance_mode": "balanced",
        "effective_runtime_mode": "cpu",
        "performance_mode_expiry": "none",
        "performance_mode_expires_at": "",
        "master_pause": False,
        "hardware_tier": "low",
        "hardware_summary": "",
    }
    try:
        # ONE bulk query covers all 5 keys; original was 5 separate
        # round trips. Operator-tunable performance — pure perf win.
        rows = dict(
            AppSetting.objects.filter(key__in=list(_RUNTIME_SETTINGS_KEYS)).values_list(
                "key", "value"
            )
        )
    except Exception:  # noqa: BLE001 — AppSetting table unavailable on cold start; defaults render the page.
        logger.debug("AppSetting table not available, using default runtime modes")
        return defaults

    expiry_raw = rows.get("system.performance_mode_expiry")
    expiry = expiry_raw if expiry_raw in ("none", "activity", "night") else "none"
    hw = _hardware_capability_snapshot()
    return {
        "runtime_mode": rows.get("system.runtime_mode") or defaults["runtime_mode"],
        "performance_mode": get_requested_performance_mode(),
        "effective_runtime_mode": _read_effective_runtime_mode(),
        "performance_mode_expiry": expiry,
        "performance_mode_expires_at": rows.get("system.performance_mode_expires_at")
        or "",
        "master_pause": (rows.get("system.master_pause") or "false").lower() == "true",
        "hardware_tier": hw["tier"],
        "hardware_summary": hw["summary"],
    }


def _hardware_capability_snapshot() -> dict[str, object]:
    """Detect hardware tier for CPU/RAM sizing.

    Defensive: hardware_profile may be unavailable in test bootstrap or
    during early app init. Falls back to a "low" tier.
    """
    try:
        from apps.pipeline.services.hardware_profile import detect_profile

        profile = detect_profile()
    except Exception:  # noqa: BLE001 — hardware probe is best-effort.
        return {
            "tier": "low",
            "summary": "Hardware probe unavailable",
        }
    return {
        "tier": profile.tier,
        "summary": profile.describe(),
    }


class RuntimeSettingsView(APIView):
    """GET /api/settings/runtime/ — current runtime mode and state.

    In addition to `runtime_mode` and `performance_mode`, also returns the
    optional expiry fields set by the time-bound chips (plan item 8). Frontend
    hydrates the chip selection from these fields on every page load so the
    user sees the same state across tabs and restarts.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return current runtime + performance + master-pause snapshot.

        Refactored 2026-05-04: was 67 lines of inline AppSetting reads.
        Now bundled into a single defensive helper that returns a typed
        snapshot on success or sane defaults on cold-start.
        """
        return Response(_runtime_settings_snapshot())


# ── RuntimeSwitchView helpers (extracted from .post) ─────────────

_PERFORMANCE_MODE_CHOICES = ("safe", "balanced", "high")
_PERFORMANCE_EXPIRY_CHOICES = ("none", "activity", "night")


def _resolve_performance_expiry_choice(*, mode: str, raw_expiry: object) -> str:
    """Performance-mode expiry only applies in ``high`` mode; force ``none`` otherwise.

    Pure function — accepts the raw value from the request body and
    returns the validated expiry string. Operator-supplied junk falls
    back to ``"none"`` so the rest of the pipeline never sees an
    unexpected value.
    """
    if mode != "high":
        return "none"
    if raw_expiry not in _PERFORMANCE_EXPIRY_CHOICES:
        return "none"
    return raw_expiry  # type: ignore[return-value]


def _persist_performance_mode_settings(
    *, mode: str, expiry: str, expires_at: str
) -> None:
    """Update the 3 ``system.performance_mode*`` AppSetting rows."""
    from apps.core.models import AppSetting

    for key, value in (
        ("system.performance_mode", mode),
        ("system.performance_mode_expiry", expiry),
        ("system.performance_mode_expires_at", expires_at or ""),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": "str",
                "category": "performance",
            },
        )


def _read_runtime_mode_setting() -> str:
    """Single-row AppSetting read for ``system.runtime_mode``; defaults to cpu."""
    from apps.core.models import AppSetting

    return (
        AppSetting.objects.filter(key="system.runtime_mode")
        .values_list("value", flat=True)
        .first()
        or "cpu"
    )


def _read_effective_runtime_mode() -> str:
    """Live runtime resolution — defaults to ``cpu`` on any failure.

    Defensive: the embeddings module is heavy + may not be importable
    on cold start. Cert-style failure mode: log + fall back to cpu so
    the dashboard chip still renders.
    """
    try:
        from apps.pipeline.services.embeddings import (
            get_effective_runtime_resolution,
        )

        return get_effective_runtime_resolution()["effective_runtime_mode"]
    except Exception:  # noqa: BLE001 — runtime resolution falls back to CPU on any failure; logger keeps a paper trail.
        logger.debug(
            "Effective runtime resolution failed; defaulting to cpu",
            exc_info=True,
        )
        return "cpu"


class RuntimeSwitchView(APIView):
    """POST /api/settings/runtime/switch/ — switch performance mode.

    Accepts:
      {
        "mode": "safe" | "balanced" | "high",
        "expiry": "none" | "activity" | "night",  # optional, only valid with mode=high
        "expires_at": "2026-04-15T06:00:00-07:00"  # optional ISO 8601 for 'night'
      }

    Backend enforcement for the expiry is `core.auto_revert_performance_mode`
    (plan items 12 + 14) running every 5 minutes via Celery Beat.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Persist a performance-mode change + its optional expiry.

        Refactored 2026-05-04: was 75 lines. Each AppSetting upsert
        + the runtime-mode read are now per-domain helpers so a future
        operator-tunable mode (e.g. 'turbo') is one edit per file.
        """
        new_mode = request.data.get("mode")
        if new_mode not in _PERFORMANCE_MODE_CHOICES:
            return Response(
                {"error": "Invalid mode. Use 'safe', 'balanced', or 'high'."},
                status=400,
            )
        new_expiry = _resolve_performance_expiry_choice(
            mode=new_mode, raw_expiry=request.data.get("expiry", "none")
        )
        new_expires_at = (
            request.data.get("expires_at", "") if new_expiry == "night" else ""
        )
        _persist_performance_mode_settings(
            mode=new_mode, expiry=new_expiry, expires_at=new_expires_at
        )
        return Response(
            {
                "runtime_mode": _read_runtime_mode_setting(),
                "performance_mode": new_mode,
                "effective_runtime_mode": _read_effective_runtime_mode(),
                "performance_mode_expiry": new_expiry,
                "performance_mode_expires_at": new_expires_at or "",
            }
        )


class RuntimeSwitchRunView(APIView):
    """POST /api/settings/runtime/switch-runtime/ — drain-and-resume runtime switch (plan item 23).

    Request body:
        {"target": "cpu", "wait_for_drain": true}

    Response mirrors ``runtime_switcher.switch_runtime`` so the UI can show
    exactly what happened (previous mode, drain seconds, warmup result).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.runtime_switcher import switch_runtime

        target = (request.data or {}).get("target", "").lower()
        wait = bool((request.data or {}).get("wait_for_drain", True))
        if target != "cpu":
            return Response(
                {"ok": False, "error": "target must be 'cpu'"}, status=400
            )
        try:
            result = switch_runtime(target=target, wait_for_drain=wait)
            return Response(result)
        except Exception:
            logger.exception("runtime switch failed")
            return Response({"ok": False, "error": "internal"}, status=500)


class RuntimeSwitchStatusView(APIView):
    """GET /api/settings/runtime/switch-status/ — current mode + any in-flight switch."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.runtime_switcher import get_switch_status

        return Response(get_switch_status())


class MasterPauseToggleView(APIView):
    """POST /api/settings/master-pause/ — flip system.master_pause (plan item 28).

    Request body (optional): {"paused": true|false}
    If the body is empty the current value is TOGGLED.

    Workers read ``system.master_pause`` at each batch boundary via
    ``apps.core.pause_contract.should_pause_now()`` (plan item 29) and stop
    taking new batches when it is truthy. Existing in-flight batches finish
    normally and save their checkpoints.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_bool = _read_master_pause_state()
        desired_raw = (request.data or {}).get("paused")
        desired_bool = (not current_bool) if desired_raw is None else bool(desired_raw)
        _persist_master_pause_state(desired_bool)
        _record_master_pause_audit_safe(request, current_bool, desired_bool)
        logger.info("master-pause toggled: %s -> %s", current_bool, desired_bool)
        return Response({"master_pause": desired_bool})


def _read_master_pause_state() -> bool:
    """Current value of ``system.master_pause`` (False if unset)."""
    from apps.core.models import AppSetting

    current = (
        AppSetting.objects.filter(key="system.master_pause")
        .values_list("value", flat=True)
        .first()
    )
    return (current or "false").lower() == "true"


def _persist_master_pause_state(desired_bool: bool) -> None:
    """Write the new master_pause value to AppSetting."""
    from apps.core.models import AppSetting

    AppSetting.objects.update_or_create(
        key="system.master_pause",
        defaults={
            "value": "true" if desired_bool else "false",
            "value_type": "bool",
            "category": "performance",
        },
    )


def _record_master_pause_audit_safe(request, previous: bool, current: bool) -> None:
    """Record audit + ops-feed for master_pause toggle. Fail-soft so the toggle
    succeeds even if audit/ops-feed are temporarily down (recorded via logger.exception)."""
    try:
        from apps.audit.services.audit_logger import record_audit
        from apps.ops_feed.services import emit

        message = (
            "Master pause enabled. Background workers will stop taking new batches."
            if current
            else "Master pause disabled. Background workers can take new batches again."
        )
        record_audit(
            "master_pause.toggle",
            ("app_setting", "system.master_pause"),
            request=request,
            message=message,
            metadata={"previous": previous, "current": current},
        )
        emit(
            "master_pause.toggled",
            message,
            source="core",
            severity="warning" if current else "success",
            related_entity_type="app_setting",
            related_entity_id="system.master_pause",
            runtime_context={"previous": previous, "current": current},
        )
    except Exception:
        logger.exception("master-pause audit emit failed")


class MaintenanceModeSettingsView(APIView):
    """GET/POST /api/settings/maintenance-mode/ — operator-visible banner toggle.

    Stored as a JSON AppSetting under ``system.maintenance_mode``. Shape:

        {"enabled": bool, "message": str, "started_at": ISO timestamp or null}

    When ``enabled`` is true the frontend shell shows a persistent amber
    banner and the active ``message``. ``started_at`` is stamped when the
    toggle flips from false -> true and cleared when it flips back.

    Kept deliberately minimal — no write-blocking middleware yet. The
    frontend half is what ships today; a future slice can add backend
    enforcement off the same flag.
    """

    permission_classes = [IsAuthenticated]

    DEFAULT_STATE = {
        "enabled": False,
        "message": "",
        "started_at": None,
    }
    _KEY = "system.maintenance_mode"

    def _get_state(self) -> dict:
        from apps.core.models import AppSetting

        try:
            setting = AppSetting.objects.get(key=self._KEY)
            stored = json.loads(setting.value or "{}")
        except AppSetting.DoesNotExist:
            stored = {}
        out = dict(self.DEFAULT_STATE)
        if isinstance(stored.get("enabled"), bool):
            out["enabled"] = stored["enabled"]
        if isinstance(stored.get("message"), str):
            out["message"] = stored["message"]
        started = stored.get("started_at")
        out["started_at"] = started if isinstance(started, str) else None
        return out

    def _write_state(self, state: dict) -> dict:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=self._KEY,
            defaults={
                "value": json.dumps(state),
                "value_type": "json",
                "category": "general",
                "description": "Maintenance-mode banner + write-gate (managed by UI).",
                "is_secret": False,
            },
        )
        return state

    def get(self, request):
        return Response(self._get_state())

    def post(self, request):
        from django.utils import timezone
        from rest_framework import status as http_status

        current = self._get_state()
        body = request.data or {}

        desired_enabled = body.get("enabled", current["enabled"])
        if not isinstance(desired_enabled, bool):
            return Response(
                {"detail": "`enabled` must be a boolean."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        desired_message = body.get("message", current["message"])
        if not isinstance(desired_message, str):
            return Response(
                {"detail": "`message` must be a string."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        started_at = current["started_at"]
        if desired_enabled and not current["enabled"]:
            started_at = timezone.now().isoformat()
        elif not desired_enabled:
            started_at = None

        new_state = {
            "enabled": desired_enabled,
            "message": desired_message,
            "started_at": started_at,
        }
        self._write_state(new_state)
        logger.info(
            "maintenance-mode flipped: enabled=%s message=%r",
            desired_enabled,
            desired_message[:80],
        )
        return Response(new_state)


class RuntimeActivityResumedView(APIView):
    """POST /api/settings/runtime/activity-resumed/ — user is active again.

    Plan item 13 ("Until I come back"). The frontend's UserActivityService
    calls this once the user starts typing/mousing after being idle while
    High Performance + 'activity' expiry was active. The call is idempotent:
    if no revert is needed the server returns {reverted: false}.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):  # noqa: D401 — simple delegating view
        try:
            from apps.core.tasks import activity_resumed_revert

            # Run synchronously so the frontend knows the final state immediately.
            # The task itself is tiny (a few DB reads + one write at most).
            result = activity_resumed_revert.apply().result
            if not isinstance(result, dict):
                result = {"reverted": False}
            return Response(result)
        except Exception:
            logger.exception("activity-resumed endpoint failed")
            return Response({"reverted": False, "error": "internal"}, status=500)


_BYTES_PER_MEGABYTE = 1024 * 1024


def _sample_cpu_ram_metrics() -> dict[str, object]:
    """Snapshot CPU% and RAM via psutil; fail-soft to null fields."""
    try:
        import psutil
    except Exception:
        logger.debug("psutil unavailable; CPU/RAM fields returned as null")
        return {
            "cpu_percent": None,
            "ram_used_mb": None,
            "ram_total_mb": None,
            "ram_percent": None,
        }
    # Non-blocking CPU sample (0s interval avoids a 1s delay per request).
    vm = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used_mb": round(vm.used / _BYTES_PER_MEGABYTE),
        "ram_total_mb": round(vm.total / _BYTES_PER_MEGABYTE),
        "ram_percent": vm.percent,
    }


class SystemMetricsView(APIView):
    """GET /api/system/metrics/ — live CPU and RAM sampling for the dashboard.

    The frontend can poll a single endpoint every 10 seconds. All fields are
    fail-soft: if psutil is unavailable, the field is null rather than raising
    an error.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_sample_cpu_ram_metrics())


class RuntimeConfigView(APIView):
    """GET/POST /api/settings/runtime-config/ — operator-safe runtime tunables."""

    permission_classes = [IsAuthenticated]

    BATCH_SIZE_MIN = 8
    BATCH_SIZE_MAX = 128
    DEFAULT_QUEUE_CONCURRENCY_MIN = 1
    DEFAULT_QUEUE_CONCURRENCY_MAX = 6
    CPU_THREAD_DEFAULT = 4
    TRUE_VALUES = {"1", "true", "yes", "on"}
    FALSE_VALUES = {"0", "false", "no", "off"}
    SETTING_DEFINITIONS = {
        "system.embedding_batch_size": {
            "value_type": "int",
            "description": "Embedding batch size used by the pipeline runtime.",
        },
        "system.gpu_memory_budget_pct": {
            "value_type": "int",
            "description": "Maximum GPU memory budget percentage for embeddings.",
        },
        "system.gpu_temp_pause_c": {
            "value_type": "int",
            "description": "GPU temperature where embedding work pauses.",
        },
        "system.cpu_encode_threads": {
            "value_type": "int",
            "description": "CPU thread cap for CPU-side embedding inference.",
        },
        "system.default_queue_concurrency": {
            "value_type": "int",
            "description": "Worker concurrency for the default Celery queue.",
        },
        "system.aggressive_oom_backoff": {
            "value_type": "bool",
            "description": "Whether embedding OOM errors automatically retry with smaller batches.",
        },
    }

    def _read_text(self, key, default=None):
        from apps.core.models import AppSetting

        value = (
            AppSetting.objects.filter(key=key).values_list("value", flat=True).first()
        )
        if value in (None, ""):
            return default
        return str(value)

    def _read_int(self, key, default):
        value = self._read_text(key, None)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _read_bool(self, key, default):
        value = self._read_text(key, None)
        if value is None:
            return default
        lowered = value.strip().lower()
        if lowered in self.TRUE_VALUES:
            return True
        if lowered in self.FALSE_VALUES:
            return False
        return default

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in self.TRUE_VALUES:
            return True
        if lowered in self.FALSE_VALUES:
            return False
        raise ValueError("Must be a boolean.")

    def _upsert_setting(self, *, key, value):
        from apps.core.models import AppSetting

        definition = self.SETTING_DEFINITIONS[key]
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": str(value),
                "value_type": definition["value_type"],
                "category": "performance",
                "description": definition["description"],
            },
        )

    def _cpu_thread_cap(self):
        import os

        logical_processors = os.cpu_count() or self.CPU_THREAD_DEFAULT
        return max(1, logical_processors - 2)

    def _default_queue_concurrency(self, django_conf):
        legacy = self._read_int("system.celery_concurrency", None)
        if legacy is not None:
            return legacy
        value = int(getattr(django_conf, "CELERY_WORKER_CONCURRENCY", 2) or 2)
        return min(
            self.DEFAULT_QUEUE_CONCURRENCY_MAX,
            max(self.DEFAULT_QUEUE_CONCURRENCY_MIN, value),
        )

    def get(self, request):
        return Response(self._runtime_config_snapshot())

    def _runtime_config_snapshot(self) -> dict[str, object]:
        """Build the GET payload — current values + valid ranges for every field."""
        from django.conf import settings as django_conf

        default_batch = int(getattr(django_conf, "EMBEDDING_BATCH_SIZE", 32) or 32)
        default_gpu_pct = int(
            float(getattr(django_conf, "CUDA_MEMORY_FRACTION_HIGH", 0.8) or 0.8) * 100
        )
        default_gpu_temp = int(getattr(django_conf, "GPU_TEMP_CEILING_C", 90) or 90)
        default_queue_concurrency = self._default_queue_concurrency(django_conf)
        cpu_thread_cap = self._cpu_thread_cap()
        default_cpu_threads = min(self.CPU_THREAD_DEFAULT, cpu_thread_cap)
        queue_concurrency = self._read_int(
            "system.default_queue_concurrency",
            default_queue_concurrency,
        )
        qc_range = [
            self.DEFAULT_QUEUE_CONCURRENCY_MIN,
            self.DEFAULT_QUEUE_CONCURRENCY_MAX,
        ]
        return {
            "embedding_batch_size": self._read_int(
                "system.embedding_batch_size", default_batch
            ),
            "gpu_memory_budget_pct": self._read_int(
                "system.gpu_memory_budget_pct", default_gpu_pct
            ),
            "gpu_temp_pause_c": self._read_int(
                "system.gpu_temp_pause_c", default_gpu_temp
            ),
            "cpu_encode_threads": self._read_int(
                "system.cpu_encode_threads", default_cpu_threads
            ),
            "default_queue_concurrency": queue_concurrency,
            "celery_concurrency": queue_concurrency,
            "aggressive_oom_backoff": self._read_bool(
                "system.aggressive_oom_backoff", True
            ),
            "embedding_batch_size_range": [self.BATCH_SIZE_MIN, self.BATCH_SIZE_MAX],
            "gpu_memory_budget_pct_range": [10, 95],
            "gpu_temp_pause_c_range": [50, 95],
            "cpu_encode_threads_range": [1, cpu_thread_cap],
            "default_queue_concurrency_range": qc_range,
            "celery_concurrency_range": qc_range,
            "default_queue_concurrency_requires_restart": True,
            "celery_concurrency_requires_restart": True,
        }

    def post(self, request):
        """Persist runtime resource settings.

        Refactored 2026-05-04: was 121 lines of repeated try/except +
        range-check blocks (one per setting). Now a single declarative
        spec table + ``_apply_int_range_setting`` helper that runs each
        rule. Behaviour preserved exactly, including the
        ``default_queue_concurrency`` / ``celery_concurrency`` alias.
        """
        updated: dict[str, object] = {}
        errors: dict[str, str] = {}
        data = request.data or {}
        for spec in self._int_field_specs():
            self._apply_int_range_setting(
                data=data, spec=spec, updated=updated, errors=errors
            )
        self._apply_queue_concurrency_alias(data, updated, errors)
        self._apply_oom_backoff(data, updated, errors)
        if errors:
            return Response({"errors": errors, "updated": updated}, status=400)
        return Response({"updated": updated})

    def _apply_queue_concurrency_alias(
        self,
        data: dict,
        updated: dict,
        errors: dict,
    ) -> None:
        """``default_queue_concurrency`` accepts the legacy ``celery_concurrency`` alias
        and broadcasts back under both names."""
        if "default_queue_concurrency" not in data and "celery_concurrency" not in data:
            return
        raw_value = data.get(
            "default_queue_concurrency",
            data.get("celery_concurrency"),
        )
        self._apply_int_range_setting(
            data={"default_queue_concurrency": raw_value},
            spec={
                "field": "default_queue_concurrency",
                "db_key": "system.default_queue_concurrency",
                "lo": self.DEFAULT_QUEUE_CONCURRENCY_MIN,
                "hi": self.DEFAULT_QUEUE_CONCURRENCY_MAX,
            },
            updated=updated,
            errors=errors,
        )
        if "default_queue_concurrency" in updated:
            updated["celery_concurrency"] = updated["default_queue_concurrency"]

    def _apply_oom_backoff(self, data: dict, updated: dict, errors: dict) -> None:
        """Persist the aggressive_oom_backoff bool setting if present in payload."""
        if "aggressive_oom_backoff" not in data:
            return
        try:
            oom_backoff = self._parse_bool(data["aggressive_oom_backoff"])
        except ValueError:
            errors["aggressive_oom_backoff"] = "Must be true or false."
            return
        self._upsert_setting(
            key="system.aggressive_oom_backoff",
            value=str(oom_backoff).lower(),
        )
        updated["aggressive_oom_backoff"] = oom_backoff

    def _int_field_specs(self) -> list[dict]:
        """Declarative spec for every int-typed resource setting on this view.

        Adding a new int field is one entry here — no copy-paste of the
        try/range/upsert dance. Each entry is ``{field, db_key, lo, hi}``;
        the loop in ``post()`` runs them all through
        ``_apply_int_range_setting``.
        """
        return [
            {
                "field": "embedding_batch_size",
                "db_key": "system.embedding_batch_size",
                "lo": self.BATCH_SIZE_MIN,
                "hi": self.BATCH_SIZE_MAX,
            },
            {
                "field": "gpu_memory_budget_pct",
                "db_key": "system.gpu_memory_budget_pct",
                "lo": 10,
                "hi": 95,
            },
            {
                "field": "gpu_temp_pause_c",
                "db_key": "system.gpu_temp_pause_c",
                "lo": 50,
                "hi": 95,
            },
            {
                "field": "cpu_encode_threads",
                "db_key": "system.cpu_encode_threads",
                "lo": 1,
                "hi": self._cpu_thread_cap(),
            },
        ]

    def _apply_int_range_setting(
        self,
        *,
        data: dict,
        spec: dict,
        updated: dict,
        errors: dict,
    ) -> None:
        """Validate one int-range setting; persist on success, record error on fail.

        Pure-function on the validate step + side-effect on the upsert
        + the in-place mutation of ``updated`` / ``errors``. Keeps the
        try/range/upsert dance in ONE place instead of repeating it
        per-field as the original 121-line handler did.
        """
        field = spec["field"]
        if field not in data:
            return
        try:
            value = int(data[field])
        except (TypeError, ValueError):
            errors[field] = "Must be an integer."
            return
        lo, hi = spec["lo"], spec["hi"]
        if not (lo <= value <= hi):
            errors[field] = f"Must be between {lo} and {hi}."
            return
        self._upsert_setting(key=spec["db_key"], value=value)
        updated[field] = value


class SafeModeBootView(APIView):
    """POST /api/system/safe-mode-boot/ — arm a flag that forces 'safe' mode on next backend startup.

    Use case: the app is misbehaving under High Performance mode and the user wants a
    one-shot recovery. Reading & clearing happens in apps.core.apps.CoreConfig.ready().
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="system.boot_safe_once",
            defaults={
                "value": "true",
                "value_type": "bool",
                "category": "performance",
            },
        )
        return Response({"armed": True, "applies_on": "next_backend_restart"})

    def get(self, request):
        from apps.core.models import AppSetting

        val = (
            AppSetting.objects.filter(key="system.boot_safe_once")
            .values_list("value", flat=True)
            .first()
        )
        return Response({"armed": str(val).lower() == "true"})

    def delete(self, request):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key="system.boot_safe_once").delete()
        return Response({"armed": False})
