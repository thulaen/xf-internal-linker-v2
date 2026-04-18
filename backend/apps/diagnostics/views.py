import hmac

from django.conf import settings

_BYTES_PER_KIB = 1024.0  # bytes per kibibyte
_SECONDS_PER_HOUR = 3600  # 60 * 60
_SECONDS_PER_DAY = 86400  # 60 * 60 * 24
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from rest_framework import status, viewsets, response, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from .models import ServiceStatusSnapshot, SystemConflict
from .serializers import (
    ServiceStatusSerializer,
    SystemConflictSerializer,
    ErrorLogSerializer,
)
from apps.audit.models import ErrorLog
from apps.core.models import AppSetting
from .health import (
    run_health_checks,
    detect_conflicts,
    get_resource_usage,
    get_feature_readinessMatrix,
    check_native_scoring,
)
from .signal_registry import SIGNALS, validate_signal_contract


class DiagnosticsOverviewView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snapshots = ServiceStatusSnapshot.objects.all()

        healthy_count = snapshots.filter(state="healthy").count()
        degraded_count = snapshots.filter(state="degraded").count()
        failed_count = snapshots.filter(state="failed").count()
        not_configured_count = snapshots.filter(state="not_configured").count()
        planned_only_count = snapshots.filter(state="planned_only").count()

        urgent_issues = SystemConflict.objects.filter(
            severity__in=["high", "critical"], resolved=False
        )[:5]
        urgent_serializer = SystemConflictSerializer(urgent_issues, many=True)

        return response.Response(
            {
                "summary": {
                    "healthy": healthy_count,
                    "degraded": degraded_count,
                    "failed": failed_count,
                    "not_configured": not_configured_count,
                    "planned_only": planned_only_count,
                },
                "top_urgent_issues": urgent_serializer.data,
            }
        )


class ServiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceStatusSnapshot.objects.exclude(service_name="http_worker")
    serializer_class = ServiceStatusSerializer
    pagination_class = None

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        results = run_health_checks()
        return response.Response(results)


class ConflictViewSet(viewsets.ModelViewSet):
    queryset = SystemConflict.objects.all()
    serializer_class = SystemConflictSerializer
    pagination_class = None

    @action(detail=False, methods=["post"])
    def detect(self, request):
        conflicts = detect_conflicts()
        return response.Response(conflicts)


class FeatureReadinessView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        matrix = get_feature_readinessMatrix()
        return response.Response(matrix)


class ResourceUsageView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        metrics = get_resource_usage()
        return response.Response(metrics)


class SystemErrorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ErrorLog.objects.all().order_by("-created_at")
    serializer_class = ErrorLogSerializer
    pagination_class = None

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        error = self.get_object()
        error.acknowledged = True
        error.save()
        return response.Response({"status": "acknowledged"})

    @action(detail=True, methods=["post"])
    def rerun(self, request, pk=None):
        """
        Phase GT Step 8 — re-dispatch the original failing Celery task.

        Supports a small whitelist of re-dispatchable job types
        (`pipeline`, `sync`, `import`). On successful dispatch the error
        row is auto-acknowledged so the Error Log clears. Out-of-scope
        job types return a Bad Request error instead of silently queuing nothing.
        """
        from apps.pipeline import tasks as pipeline_tasks

        error = self.get_object()
        known = {
            "pipeline": getattr(pipeline_tasks, "run_pipeline", None),
            "sync": getattr(pipeline_tasks, "sync_single_xf_item", None),
            "import": getattr(pipeline_tasks, "dispatch_import_content", None),
        }
        task = known.get(error.job_type)
        if task is None:
            return response.Response(
                {
                    "detail": (
                        f"Job type '{error.job_type}' is not currently "
                        "rerun-able from the UI."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if hasattr(task, "delay"):
                task.delay()
            else:
                task()
        except Exception as exc:  # noqa: BLE001
            return response.Response(
                {"status": "error", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        error.acknowledged = True
        error.save(update_fields=["acknowledged"])
        return response.Response({"status": "queued", "acknowledged": True})


# ── Phase GT Step 5 — operator intelligence endpoints ──────────────────────


class RuntimeContextView(views.APIView):
    """
    Snapshot of the current runtime — GPU / CUDA / embedding / spaCy /
    node. Consumed by the Live Runtime Health strip at the top of the
    Diagnostics Error Log.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.audit.runtime_context import snapshot as runtime_snapshot

        return response.Response(runtime_snapshot())


class NodesView(views.APIView):
    """
    One row per known node (primary + every slave that has written an
    ErrorLog in the last 24 hours). Powers the GT-G13 nodes strip on
    the Diagnostics page. No separate heartbeat table — slaves self-
    announce by writing errors tagged with their NODE_ID env var.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        import socket

        from django.db.models import Count, Max, Q

        since = timezone.now() - timedelta(hours=24)
        nodes = (
            ErrorLog.objects.filter(created_at__gte=since)
            .values("node_id", "node_role", "node_hostname")
            .annotate(
                last_seen=Max("created_at"),
                unacknowledged=Count("id", filter=Q(acknowledged=False)),
                total=Count("id"),
                worst_severity=Max("severity"),
            )
            .order_by("-last_seen")
        )
        primary_id = os.environ.get("NODE_ID", socket.gethostname())
        payload = list(nodes)
        if primary_id not in {n["node_id"] for n in payload}:
            payload.insert(
                0,
                {
                    "node_id": primary_id,
                    "node_role": "primary",
                    "node_hostname": socket.gethostname(),
                    "last_seen": None,
                    "unacknowledged": 0,
                    "total": 0,
                    "worst_severity": "low",
                },
            )
        return response.Response(payload)


class SignalQueueView(views.APIView):
    """
    Phase SEQ — ranking signal execution queue visibility.

    Returns the current lock-holder (if any) and the list of pending
    signal-compute tasks. Consumed by:
    - Mission Critical "Ranking Signals" tile (Phase MC)
    - Meta Algorithm Settings tab "Run now" button (Phase MS)
    - Operations Feed signal-start/finish events (Phase OF)

    No new backend state — reads directly from the `task_lock.py`
    cache namespace. Pending task count is a stub today (Celery doesn't
    expose queue inspection without broker introspection tools); a
    follow-up can populate it via `celery inspect scheduled` data.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.pipeline.services.task_lock import get_active_locks
        from django.core.cache import cache

        locks = get_active_locks()
        signal_holder = locks.get("signal")

        # Phase MX1 extras — read Celery's scheduled/reserved queues via
        # the inspect API when available. Best-effort: if Celery isn't
        # reachable we still return the running holder so the UI doesn't
        # flash empty.
        queued: list[dict] = []
        queue_depth = 0
        try:
            from config.celery import app as celery_app

            inspector = celery_app.control.inspect(timeout=0.3)
            scheduled = inspector.scheduled() or {}
            reserved = inspector.reserved() or {}
            for worker_entries in (*scheduled.values(), *reserved.values()):
                for entry in worker_entries or []:
                    task = entry.get("request", entry)
                    task_name = (task.get("name") or "").split(".")[-1]
                    if task_name.startswith("compute_signal_"):
                        queued.append(
                            {
                                "task": task_name,
                                "id": task.get("id"),
                                "eta": task.get("eta"),
                            }
                        )
            queue_depth = len(queued)
        except Exception:  # noqa: BLE001
            pass

        # Phase MX1 / Gap 288 — total queue ETA, based on a coarse
        # `avg_signal_ms` hint cached by recent completions.
        avg_ms = cache.get("signal_exec:avg_ms", 30_000)
        eta_total_ms = queue_depth * int(avg_ms)

        # Phase MX1 / Gap 289 — last-run-per-signal map kept in cache by
        # the wrapper on completion.
        last_run_map: dict = cache.get("signal_exec:last_run", {}) or {}

        return response.Response(
            {
                "running": signal_holder,
                "queued": queued,
                "queue_depth": queue_depth,
                "eta_total_ms": eta_total_ms,
                "avg_signal_ms": avg_ms,
                "last_run": last_run_map,
                "lock_class": "signal",
                "pause_after_current": bool(
                    cache.get("signal_exec:pause_after_current", False)
                ),
                "other_lock_holders": {
                    wc: holder
                    for wc, holder in locks.items()
                    if wc != "signal" and holder
                },
            }
        )

    def post(self, request):
        """Phase MX1 — operator controls for the signal queue.

        Payload: `{"action": "pause_after_current"|"resume"|"abort_all"}`.
        All three manipulate a small set of cache flags the decorator
        + future queue-scheduler consult on every run boundary.
        """
        from django.core.cache import cache

        action = (request.data.get("action") or "").strip()
        if action == "pause_after_current":
            cache.set("signal_exec:pause_after_current", True, timeout=3600)
            return response.Response({"status": "pause-after-current queued"})
        if action == "resume":
            cache.delete("signal_exec:pause_after_current")
            return response.Response({"status": "resumed"})
        if action == "abort_all":
            # Typed-string confirmation happens client-side; server just
            # publishes the flag. A future scheduler pass drains the queue
            # at the next lock-acquisition attempt.
            cache.set("signal_exec:abort_all", True, timeout=300)
            return response.Response({"status": "abort-all flag set"})
        return response.Response(
            {"detail": f"unknown action: {action}"},
            status=status.HTTP_400_BAD_REQUEST,
        )


class PipelineGateView(views.APIView):
    """
    GT-G14 — single go/no-go verdict for the ranking pipeline.

    Reuses the existing checks in apps.health.services — does NOT
    introduce new detection logic. Returns `can_run` + a list of
    `blockers` each with plain-English explanation and next step, so
    the UI banner can render the fix instructions directly.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.health.services import (
            check_celery_health,
            check_gpu_faiss_health,
            check_ml_models_health,
        )

        checks = (
            ("GPU (FAISS)", check_gpu_faiss_health),
            ("ML models", check_ml_models_health),
            ("Celery worker", check_celery_health),
        )
        blockers = []
        for check_name, fn in checks:
            try:
                result = fn()
                data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            except Exception as exc:  # noqa: BLE001
                blockers.append(
                    {
                        "check": check_name,
                        "state": "failed",
                        "explanation": str(exc),
                        "next_step": "",
                    }
                )
                continue

            state = str(data.get("status") or data.get("state") or "unknown")
            if state not in ("healthy", "not_configured", "degraded"):
                blockers.append(
                    {
                        "check": check_name,
                        "state": state,
                        "explanation": data.get("issue_description")
                        or data.get("explanation", ""),
                        "next_step": data.get("suggested_fix")
                        or data.get("next_action_step", ""),
                    }
                )
        return response.Response({"can_run": len(blockers) == 0, "blockers": blockers})


class SchedulerDispatchView(views.APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        configured_token = getattr(settings, "SCHEDULER_CONTROL_TOKEN", "")
        request_token = request.headers.get("X-Scheduler-Token", "")

        if not configured_token:
            return response.Response(
                {
                    "detail": "Scheduler control token is missing, so Django cannot trust scheduler-triggered dispatch.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not hmac.compare_digest(configured_token, request_token):
            return response.Response(
                {
                    "detail": "Scheduler control token did not match.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        task_name = str(request.data.get("task") or "").strip()
        kwargs = request.data.get("kwargs") or {}
        periodic_task_name = str(request.data.get("periodic_task_name") or "").strip()

        if not isinstance(kwargs, dict):
            return response.Response(
                {"detail": "Scheduler kwargs must be a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if task_name == "pipeline.import_content":
            from apps.pipeline.tasks import dispatch_import_content

            result = dispatch_import_content(
                scope_ids=kwargs.get("scope_ids"),
                mode=str(kwargs.get("mode") or "full"),
                source=str(kwargs.get("source") or "api"),
                file_path=kwargs.get("file_path"),
                job_id=kwargs.get("job_id"),
                force_reembed=bool(kwargs.get("force_reembed") or False),
            )
            return response.Response(
                {
                    "status": "queued",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    **result,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if task_name == "pipeline.nightly_data_retention":
            from apps.pipeline.tasks import nightly_data_retention

            result = nightly_data_retention.run()
            return response.Response(
                {
                    "status": "completed",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    "result": result,
                },
                status=status.HTTP_200_OK,
            )

        if task_name == "pipeline.cleanup_stuck_sync_jobs":
            from apps.pipeline.tasks import cleanup_stuck_sync_jobs

            result = cleanup_stuck_sync_jobs.run()
            return response.Response(
                {
                    "status": "completed",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    "result": result,
                },
                status=status.HTTP_200_OK,
            )

        return response.Response(
            {
                "detail": (
                    f"Scheduler task '{task_name}' is not supported by the Django control plane yet. "
                    "Add an explicit dispatcher before letting the C# scheduler own it."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class MetaTournamentView(views.APIView):
    """
    FR-225: Meta Tournament diagnostics.

    GET  /api/system/status/meta-tournament/         — summary per slot
    POST /api/system/status/meta-tournament/run/     — trigger a manual run
    POST /api/system/status/meta-tournament/pin/     — operator pin a winner
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import MetaTournamentResult
        from apps.suggestions.services.meta_slot_registry import META_SLOT_REGISTRY

        slots = []
        for slot_id, config in META_SLOT_REGISTRY.items():
            # Last winner
            last_winner = (
                MetaTournamentResult.objects.filter(slot_id=slot_id, was_winner=True)
                .order_by("-evaluated_at")
                .first()
            )
            # Last tournament date
            last_run = (
                MetaTournamentResult.objects.filter(slot_id=slot_id)
                .order_by("-evaluated_at")
                .values_list("evaluated_at", flat=True)
                .first()
            )
            # Promotion history (last 10)
            promotions = list(
                MetaTournamentResult.objects.filter(slot_id=slot_id, was_winner=True)
                .order_by("-evaluated_at")
                .values(
                    "meta_id",
                    "evaluated_at",
                    "ndcg_at_10",
                    "ndcg_delta",
                    "previous_winner",
                    "queries_evaluated",
                )[:10]
            )

            slots.append(
                {
                    "slot_id": slot_id,
                    "rotation_mode": config.rotation_mode,
                    "description": config.description,
                    "pinned": config.pinned,
                    "active_winner": config.active_default,
                    "members": config.members,
                    "last_tournament_date": last_run,
                    "last_winner": {
                        "meta_id": last_winner.meta_id,
                        "ndcg_at_10": last_winner.ndcg_at_10,
                        "evaluated_at": last_winner.evaluated_at,
                        "queries_evaluated": last_winner.queries_evaluated,
                    }
                    if last_winner
                    else None,
                    "promotion_history": promotions,
                }
            )

        return response.Response(
            {
                "slots": slots,
                "total_slots": len(slots),
                "single_active_slots": sum(
                    1 for s in slots if s["rotation_mode"] == "single_active"
                ),
                "all_active_slots": sum(
                    1 for s in slots if s["rotation_mode"] == "all_active"
                ),
                "pinned_slots": sum(1 for s in slots if s["pinned"]),
            }
        )


class MetaTournamentRunView(views.APIView):
    """POST — trigger a manual tournament run (optionally for a single slot)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.suggestions.services.meta_rotation_scheduler import (
            meta_rotation_tournament,
        )

        slot_id = request.data.get("slot_id") or None
        task = meta_rotation_tournament.delay(slot_id=slot_id)
        return response.Response(
            {
                "status": "queued",
                "task_id": task.id,
                "slot_id": slot_id or "ALL",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MetaTournamentPinView(views.APIView):
    """POST — operator pin/unpin a winner for a slot."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.suggestions.services.meta_slot_registry import META_SLOT_REGISTRY

        slot_id = str(request.data.get("slot_id") or "").strip()
        pin = bool(request.data.get("pinned", True))

        if slot_id not in META_SLOT_REGISTRY:
            return response.Response(
                {"detail": f"Unknown slot_id '{slot_id}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        META_SLOT_REGISTRY[slot_id].pinned = pin
        return response.Response(
            {
                "slot_id": slot_id,
                "pinned": META_SLOT_REGISTRY[slot_id].pinned,
                "active_winner": META_SLOT_REGISTRY[slot_id].active_default,
            }
        )


class WeightDiagnosticsView(views.APIView):
    """
    FR-028: Algorithm Weight Diagnostics.
    Provides a read-only view of all 23 ranking and value model signals,
    their current weights, storage usage, and C++ acceleration status.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Fetch current settings/weights
        settings = {s.key: s.value for s in AppSetting.objects.all()}

        # 2. Get C++ status
        _state, _expl, _step, native_metadata = check_native_scoring()
        cpp_module_map = {
            m["module"]: m for m in native_metadata.get("module_statuses", [])
        }

        # 3. Get recent error counts per area (last 24h)
        yesterday = timezone.now() - timedelta(hours=24)
        error_counts = {}
        # Simple heuristic: map signal keywords to job_type or step
        logs = ErrorLog.objects.filter(created_at__gte=yesterday, acknowledged=False)
        for log in logs:
            key = f"{log.job_type}:{log.step}".lower()
            error_counts[key] = error_counts.get(key, 0) + 1

        # 4. Gather storage stats for referenced tables
        table_stats = self._get_table_stats()

        # 5. Build final payload
        signal_data = []
        for sig in SIGNALS:
            # Resolve weight
            weight_val = (
                settings.get(sig.weight_key, "0.0") if sig.weight_key else "N/A"
            )
            try:
                weight_display = float(weight_val) if weight_val != "N/A" else 0.0
            except ValueError:
                weight_display = weight_val

            # Resolve C++ status
            cpp_active = False
            cpp_status = "Not Supported"
            if sig.cpp_kernel:
                mod_name = sig.cpp_kernel.split(".")[0]
                mod_info = cpp_module_map.get(mod_name)
                if mod_info:
                    cpp_active = mod_info.get("state") == "healthy"
                    cpp_status = (
                        "Active (C++)" if cpp_active else "Degraded (Python Fallback)"
                    )
                else:
                    cpp_status = "Available (Not Loaded)"

            # Resolve storage
            # sig.table_name might contain multiple tables or extra info, take first word as table name
            raw_table = sig.table_name.split(" ")[0].lower()
            stats = table_stats.get(raw_table, {"rows": 0, "size_bytes": 0})

            # Resolve errors
            # Look for signal ID or job_type matches in error_counts
            err_count = 0
            for err_key, count in error_counts.items():
                if sig.id.lower() in err_key or (
                    sig.cpp_kernel and sig.cpp_kernel.split(".")[0].lower() in err_key
                ):
                    err_count += count

            signal_data.append(
                {
                    "id": sig.id,
                    "name": sig.name,
                    "type": sig.type,
                    "description": sig.description,
                    "weight": weight_display,
                    "cpp_acceleration": {
                        "active": cpp_active,
                        "status_label": cpp_status,
                        "kernel": sig.cpp_kernel,
                    },
                    "storage": {
                        "table": raw_table,
                        "row_count": stats["rows"],
                        "size_bytes": stats["size_bytes"],
                        "size_human": self._human_size(stats["size_bytes"]),
                    },
                    "health": {
                        "status": "healthy" if err_count == 0 else "degraded",
                        "recent_errors": err_count,
                    },
                    "governance": {
                        "status": sig.status,
                        "fr_id": sig.fr_id,
                        "spec_path": sig.spec_path,
                        "academic_source": sig.academic_source,
                        "source_kind": sig.source_kind,
                        "architecture_lane": sig.architecture_lane,
                        "neutral_value": sig.neutral_value,
                        "min_data_threshold": sig.min_data_threshold,
                        "diagnostic_surfaces": list(sig.diagnostic_surfaces),
                        "benchmark_module": sig.benchmark_module,
                        "autotune_included": sig.autotune_included,
                        "default_enabled": sig.default_enabled,
                        "added_in_phase": sig.added_in_phase,
                    },
                }
            )

        contract_violations = validate_signal_contract()
        return response.Response(
            {
                "signals": signal_data,
                "summary": {
                    "total_signals": len(SIGNALS),
                    "active_signals": sum(1 for s in SIGNALS if s.status == "active"),
                    "cpp_accelerated_count": sum(
                        1 for s in signal_data if s["cpp_acceleration"]["active"]
                    ),
                    "healthy_count": sum(
                        1 for s in signal_data if s["health"]["status"] == "healthy"
                    ),
                    "contract_violations": contract_violations,
                    "contract_clean": len(contract_violations) == 0,
                    "last_refreshed": timezone.now(),
                },
            }
        )

    def _get_table_stats(self):
        """Fetch row counts and disk usage for core algorithm tables."""
        tables = [
            "content_contentitem",
            "content_sentence",
            "graph_existinglink",
            "analytics_searchmetric",
            "analytics_suggestiontelemetrydaily",
            "cooccurrence_sessioncooccurrencepair",
            "graph_clickdistance",
            "audit_errorlog",
        ]
        stats = {}
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Get approximate row count and total size including indexes
                    cursor.execute(
                        """
                        SELECT 
                            (reltuples)::bigint AS row_count,
                            pg_total_relation_size(quote_ident(relname)) AS total_bytes
                        FROM pg_class
                        WHERE relname = %s;
                    """,
                        [table],
                    )
                    row = cursor.fetchone()
                    if row:
                        stats[table] = {"rows": row[0], "size_bytes": row[1]}
                    else:
                        stats[table] = {"rows": 0, "size_bytes": 0}
                except Exception:
                    stats[table] = {"rows": 0, "size_bytes": 0}
        return stats

    def _human_size(self, bytes_val):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < _BYTES_PER_KIB:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= _BYTES_PER_KIB
        return f"{bytes_val:.1f} PB"


class MissionCriticalView(views.APIView):
    """Phase MC — single aggregator the dashboard's Mission Critical tab reads.

    Returns a flat list of tile descriptors. Each tile entry is:

        {
            "id": "pipeline",
            "name": "Pipeline",
            "state": "WORKING" | "IDLE" | "PAUSED" | "DEGRADED" | "FAILED",
            "plain_english": "One-line status.",
            "last_action_at": "ISO8601" | None,
            "progress": 0..1 | None,
            "actions": ["Resume", "Pause", ...],
            "group": "algorithms" | None,
            "root_cause": "<tile_id>" | None,
        }

    Dedup rules (from the approved plan):
      * When the pipeline gate is blocked, dependent tiles (pipeline /
        embeddings / signals / meta / cooccurrence) mark `root_cause` =
        'pipeline_gate' so the UI collapses them under the root.
      * The five meta-algorithm tiles are flagged with `group='algorithms'`
        so the UI can render one green summary row when all five are
        healthy, expanding only on degrade.

    Reuses existing health checks + AppSettings — no new telemetry.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.pipeline.services.task_lock import get_active_locks
        from apps.suggestions.readiness import assemble_prerequisites

        locks = get_active_locks()
        tiles: list[dict] = []

        # ── Pipeline ─────────────────────────────────────────────
        heavy_holder = locks.get("heavy")
        master_pause = _read_master_pause()
        if master_pause:
            tiles.append(
                _tile(
                    "pipeline",
                    "Pipeline",
                    "PAUSED",
                    "Master pause active — workers at safe checkpoint.",
                    actions=["Resume"],
                )
            )
        elif heavy_holder:
            tiles.append(
                _tile(
                    "pipeline",
                    "Pipeline",
                    "WORKING",
                    f"Running: {_owner_label(heavy_holder)}.",
                    actions=["Pause"],
                )
            )
        else:
            tiles.append(
                _tile(
                    "pipeline",
                    "Pipeline",
                    "IDLE",
                    "No heavy task currently running.",
                    actions=["Pause"],
                )
            )

        # ── Ranking signals (Phase SEQ namespace) ────────────────
        signal_holder = locks.get("signal")
        if signal_holder:
            tiles.append(
                _tile(
                    "signals",
                    "Ranking signals",
                    "WORKING",
                    f"Computing {_owner_label(signal_holder)}.",
                    actions=["Pause"],
                )
            )
        else:
            tiles.append(
                _tile(
                    "signals",
                    "Ranking signals",
                    "IDLE",
                    "Signal queue empty — no compute in flight.",
                )
            )

        # ── Embeddings ────────────────────────────────────────────
        tiles.append(_embeddings_tile())
        tiles.append(_model_runtime_tile())
        tiles.append(_helper_nodes_tile())
        tiles.append(_anti_spam_tile())

        # ── Algorithms accordion ─────────────────────────────────
        tiles.append(_meta_tile_native_scoring())
        tiles.append(_meta_tile_slate_diversity())
        tiles.append(_meta_tile_weight_tuning())
        tiles.append(_meta_tile_attribution())
        tiles.append(_meta_tile_cooccurrence())

        # ── External data sources ────────────────────────────────
        tiles.append(_external_tile("gsc", "Google Search Console"))
        tiles.append(_external_tile("ga4", "Google Analytics 4"))
        tiles.append(_external_tile("matomo", "Matomo"))

        # ── Crawler + Import + Webhooks ──────────────────────────
        tiles.append(_crawler_tile())
        tiles.append(_import_tile())
        tiles.append(_webhooks_tile())

        # ── Suggestion Readiness (Phase SR) ──────────────────────
        prereqs = assemble_prerequisites()
        blocking = [p for p in prereqs if p["status"] != "ready"]
        if not blocking:
            tiles.append(
                _tile(
                    "suggestion_readiness",
                    "Suggestion readiness",
                    "WORKING",
                    "All prerequisites ready.",
                )
            )
        else:
            first = blocking[0]
            mc_state = "DEGRADED" if first["status"] != "blocked" else "FAILED"
            tiles.append(
                _tile(
                    "suggestion_readiness",
                    "Suggestion readiness",
                    mc_state,
                    f"Blocking: {first['name']} — {first['plain_english']}",
                )
            )

        # ── Root-cause dedup ─────────────────────────────────────
        for p in prereqs:
            if p["id"] == "pipeline_gate" and p["status"] == "blocked":
                for tile in tiles:
                    if (
                        tile["id"] in ("pipeline", "signals", "embeddings")
                        or tile.get("group") == "algorithms"
                    ):
                        tile["root_cause"] = "pipeline_gate"

        return response.Response(
            {
                "tiles": tiles,
                "updated_at": timezone.now().isoformat(),
            }
        )


# ── MC helpers ───────────────────────────────────────────────────────


def _tile(
    tile_id: str,
    name: str,
    state: str,
    plain_english: str,
    *,
    actions: list[str] | None = None,
    group: str | None = None,
    progress: float | None = None,
    last_action_at=None,
) -> dict:
    return {
        "id": tile_id,
        "name": name,
        "state": state,
        "plain_english": plain_english,
        "last_action_at": last_action_at.isoformat() if last_action_at else None,
        "progress": progress,
        "actions": actions or [],
        "group": group,
        "root_cause": None,
    }


def _owner_label(raw) -> str:
    if not raw:
        return "task"
    s = str(raw)
    return s.split(":", 1)[0] if ":" in s else s


def _read_master_pause() -> bool:
    row = AppSetting.objects.filter(key="system.master_pause").first()
    if row is None:
        return False
    return str(row.value).strip().lower() in ("1", "true", "yes", "on")


def _embeddings_tile() -> dict:
    try:
        from apps.content.models import ContentItem
        from apps.core.runtime_registry import (
            summarize_helpers,
            summarize_model_registry,
        )

        runtime = summarize_model_registry()
        helpers = summarize_helpers()
        active_model = runtime.get("active_model") or {}
        model_name = active_model.get("model_name") or "BAAI/bge-m3"
        dimension = active_model.get("dimension")
        device = active_model.get("device_target") or runtime.get("device") or "cpu"
        helper_assisted = bool(
            helpers.get("counts", {}).get("online", 0)
            or helpers.get("counts", {}).get("busy", 0)
        )
        model_label = f"{model_name} on {device}"
        if dimension:
            model_label = f"{model_label} ({dimension}d)"

        total = ContentItem.objects.count()
        if total == 0:
            return _tile(
                "embeddings",
                "Embeddings",
                "IDLE",
                f"No in-scope content yet. Active model: {model_label}.",
            )
        missing = ContentItem.objects.filter(embedding__isnull=True).count()
        if missing == 0:
            return _tile(
                "embeddings",
                "Embeddings",
                "WORKING",
                (
                    f"All {total:,} items embedded with {model_label}. "
                    f"Helper-assisted: {'yes' if helper_assisted else 'no'}."
                ),
                progress=1.0,
            )
        done = total - missing
        return _tile(
            "embeddings",
            "Embeddings",
            "WORKING",
            (
                f"{done:,} of {total:,} items embedded with {model_label}. "
                f"Helper-assisted: {'yes' if helper_assisted else 'no'}."
            ),
            actions=["Pause"],
            progress=done / total,
        )
    except Exception:  # noqa: BLE001
        return _tile(
            "embeddings",
            "Embeddings",
            "DEGRADED",
            "Could not read embedding state.",
        )


def _model_runtime_tile() -> dict:
    try:
        from apps.core.runtime_registry import summarize_model_registry

        summary = summarize_model_registry()
        active_model = summary.get("active_model") or {}
        candidate_model = summary.get("candidate_model") or {}
        backfill = summary.get("backfill") or {}
        active_name = active_model.get("model_name") or "Unknown model"
        active_status = active_model.get("status") or "unknown"
        device = active_model.get("device_target") or summary.get("device") or "cpu"

        if active_status in {"failed", "deleted"}:
            return _tile(
                "model_runtime",
                "Model runtime",
                "FAILED",
                (
                    f"{active_name} is {active_status} on {device}. "
                    "Open Settings > Runtime to warm, roll back, or replace it."
                ),
            )
        if backfill and backfill.get("status") in {"queued", "running", "paused"}:
            return _tile(
                "model_runtime",
                "Model runtime",
                "DEGRADED",
                (
                    f"{active_name} is active on {device}, and a backfill is "
                    f"{backfill.get('status')}."
                ),
                actions=["Pause", "Resume"],
                progress=(backfill.get("progress_pct") or 0.0) / 100.0,
            )
        if candidate_model:
            return _tile(
                "model_runtime",
                "Model runtime",
                "DEGRADED",
                (
                    f"{active_name} is champion on {device}. Candidate "
                    f"{candidate_model.get('model_name')} is "
                    f"{candidate_model.get('status')}."
                ),
                actions=["Resume"],
            )
        return _tile(
            "model_runtime",
            "Model runtime",
            "WORKING",
            f"{active_name} is the active embedding model on {device}. Hot swap is ready.",
        )
    except Exception:  # noqa: BLE001
        return _tile(
            "model_runtime",
            "Model runtime",
            "DEGRADED",
            "Could not read model runtime state.",
        )


def _helper_nodes_tile() -> dict:
    try:
        from apps.core.runtime_registry import summarize_helpers

        summary = summarize_helpers()
        counts = summary.get("counts") or {}
        online = int(counts.get("online", 0))
        busy = int(counts.get("busy", 0))
        stale = int(counts.get("stale", 0))
        offline = int(counts.get("offline", 0))
        aggregate_ram_pressure = float(summary.get("aggregate_ram_pressure") or 0.0)
        busiest = summary.get("busiest") or {}

        if online == 0 and busy == 0 and stale == 0 and offline == 0:
            return _tile(
                "helper_nodes",
                "Helper nodes",
                "IDLE",
                "No helper nodes configured. The primary machine is handling all work.",
            )
        if online == 0 and busy == 0:
            state = "FAILED" if stale == 0 else "DEGRADED"
            return _tile(
                "helper_nodes",
                "Helper nodes",
                state,
                (
                    f"No helpers are available right now. Counts: online {online}, "
                    f"busy {busy}, stale {stale}, offline {offline}."
                ),
            )
        if aggregate_ram_pressure >= 0.9:
            return _tile(
                "helper_nodes",
                "Helper nodes",
                "DEGRADED",
                (
                    f"Helpers are online, but RAM pressure is high "
                    f"({aggregate_ram_pressure:.0%}). Busiest: "
                    f"{busiest.get('name') or 'n/a'}."
                ),
                progress=aggregate_ram_pressure,
            )
        return _tile(
            "helper_nodes",
            "Helper nodes",
            "WORKING",
            (
                f"Online {online}, busy {busy}, stale {stale}, offline {offline}. "
                f"Busiest load: {(busiest.get('effective_load') or 0.0):.0%}."
            ),
            progress=aggregate_ram_pressure,
        )
    except Exception:  # noqa: BLE001
        return _tile(
            "helper_nodes",
            "Helper nodes",
            "DEGRADED",
            "Could not read helper node state.",
        )


def _anti_spam_tile() -> dict:
    try:
        from apps.core.views_antispam import (
            get_anchor_diversity_settings,
            get_keyword_stuffing_settings,
            get_link_farm_settings,
        )

        signals = {
            "Anchor diversity": get_anchor_diversity_settings(),
            "Keyword stuffing": get_keyword_stuffing_settings(),
            "Link farm": get_link_farm_settings(),
        }
        disabled = [
            name for name, cfg in signals.items() if not bool(cfg.get("enabled"))
        ]
        zero_weight = [
            name
            for name, cfg in signals.items()
            if float(cfg.get("ranking_weight") or 0.0) <= 0.0
        ]
        if disabled:
            return _tile(
                "anti_spam",
                "Anti-spam",
                "DEGRADED",
                (
                    f"Disabled signals: {', '.join(disabled)}. Open Settings to "
                    "restore the default anti-spam stack."
                ),
            )
        if zero_weight:
            return _tile(
                "anti_spam",
                "Anti-spam",
                "DEGRADED",
                (
                    f"Zero-weight signals: {', '.join(zero_weight)}. Recommended "
                    "preset expects all three penalties to stay active."
                ),
            )
        return _tile(
            "anti_spam",
            "Anti-spam",
            "WORKING",
            (
                "Anchor diversity, keyword stuffing, and link-farm penalties are "
                "enabled with active weights."
            ),
        )
    except Exception:  # noqa: BLE001
        return _tile(
            "anti_spam",
            "Anti-spam",
            "DEGRADED",
            "Could not read anti-spam settings.",
        )


def _health_state_to_mc(state: str) -> str:
    if state == "healthy":
        return "WORKING"
    if state in ("degraded", "stale"):
        return "DEGRADED"
    if state in ("down", "error", "failed"):
        return "FAILED"
    if state == "not_configured":
        return "IDLE"
    return "IDLE"


def _meta_tile_native_scoring() -> dict:
    from apps.diagnostics import health as dh

    state, explanation, _next, _meta = dh.check_native_scoring()
    tile = _tile(
        "cpp_hot_path",
        "C++ hot path",
        _health_state_to_mc(state),
        explanation,
        group="algorithms",
    )
    tile["kernel_names"] = [label for _, _, label, _ in dh._NATIVE_RUNTIME_MODULES]
    return tile


def _meta_tile_slate_diversity() -> dict:
    from apps.diagnostics import health as dh

    state, explanation, _next, _meta = dh.check_slate_diversity_runtime()
    return _tile(
        "slate_diversity",
        "Slate diversity",
        _health_state_to_mc(state),
        explanation,
        group="algorithms",
    )


def _meta_tile_weight_tuning() -> dict:
    last = _read_datetime_setting("system.last_weight_tune_at")
    if last is None:
        return _tile(
            "weight_tuning",
            "Weight tuning",
            "IDLE",
            "Weight tuner has never run.",
            actions=["Run now"],
            group="algorithms",
        )
    age = timezone.now() - last
    if age <= timedelta(days=31):
        return _tile(
            "weight_tuning",
            "Weight tuning",
            "WORKING",
            f"Last tune {_humanize_age(age)}.",
            actions=["Run now"],
            group="algorithms",
            last_action_at=last,
        )
    return _tile(
        "weight_tuning",
        "Weight tuning",
        "DEGRADED",
        f"Last tune {_humanize_age(age)} — overdue.",
        actions=["Run now"],
        group="algorithms",
        last_action_at=last,
    )


def _meta_tile_attribution() -> dict:
    last = _read_datetime_setting("system.last_attribution_run_at")
    if last is None:
        return _tile(
            "attribution",
            "Attribution",
            "IDLE",
            "Attribution engine has never run.",
            actions=["Recompute"],
            group="algorithms",
        )
    age = timezone.now() - last
    if age <= timedelta(hours=12):
        return _tile(
            "attribution",
            "Attribution",
            "WORKING",
            f"Attribution computed {_humanize_age(age)}.",
            actions=["Recompute"],
            group="algorithms",
            last_action_at=last,
        )
    return _tile(
        "attribution",
        "Attribution",
        "DEGRADED",
        f"Attribution last computed {_humanize_age(age)}.",
        actions=["Recompute"],
        group="algorithms",
        last_action_at=last,
    )


def _meta_tile_cooccurrence() -> dict:
    try:
        from apps.cooccurrence.models import SessionCooccurrencePair
        from django.db.models import Max

        latest = SessionCooccurrencePair.objects.aggregate(m=Max("updated_at"))["m"]
        if latest is None:
            return _tile(
                "cooccurrence",
                "Cooccurrence",
                "IDLE",
                "Cooccurrence table is empty.",
                actions=["Rebuild"],
                group="algorithms",
            )
        age = timezone.now() - latest
        if age <= timedelta(hours=24):
            return _tile(
                "cooccurrence",
                "Cooccurrence",
                "WORKING",
                f"Pairs refreshed {_humanize_age(age)}.",
                actions=["Rebuild"],
                group="algorithms",
                last_action_at=latest,
            )
        return _tile(
            "cooccurrence",
            "Cooccurrence",
            "DEGRADED",
            f"Pairs last refreshed {_humanize_age(age)}.",
            actions=["Rebuild"],
            group="algorithms",
            last_action_at=latest,
        )
    except Exception:  # noqa: BLE001
        return _tile(
            "cooccurrence",
            "Cooccurrence",
            "DEGRADED",
            "Could not read cooccurrence state.",
            actions=["Rebuild"],
            group="algorithms",
        )


def _external_tile(source_id: str, name: str) -> dict:
    from apps.diagnostics import health as dh

    checker = {"gsc": dh.check_gsc, "ga4": dh.check_ga4, "matomo": dh.check_matomo}[
        source_id
    ]
    state, explanation, _next, _meta = checker()
    mc_state = _health_state_to_mc(state)
    actions = ["Reconnect"] if mc_state in ("DEGRADED", "FAILED") else []
    return _tile(source_id, name, mc_state, explanation, actions=actions)


def _crawler_tile() -> dict:
    try:
        from apps.crawler.models import CrawlSession

        latest = CrawlSession.objects.order_by("-started_at").first()
        if latest is None:
            return _tile(
                "crawler",
                "Crawler",
                "IDLE",
                "No crawl sessions yet.",
            )
        state_raw = getattr(latest, "state", "") or getattr(latest, "status", "")
        mc_state = {
            "running": "WORKING",
            "paused": "PAUSED",
            "completed": "IDLE",
            "failed": "FAILED",
        }.get(state_raw, "IDLE")
        return _tile(
            "crawler",
            "Crawler",
            mc_state,
            f"Last session: {state_raw or 'unknown'}.",
            actions=["Pause", "Resume"] if mc_state in ("WORKING", "PAUSED") else [],
        )
    except Exception:  # noqa: BLE001
        return _tile("crawler", "Crawler", "IDLE", "No crawler state available.")


def _import_tile() -> dict:
    try:
        from apps.sync.models import SyncJob

        latest = SyncJob.objects.order_by("-started_at").first()
        if latest is None:
            return _tile("imports", "Imports", "IDLE", "No import jobs yet.")
        state_raw = getattr(latest, "state", "") or getattr(latest, "status", "")
        mc_state = {
            "running": "WORKING",
            "paused": "PAUSED",
            "completed": "IDLE",
            "success": "IDLE",
            "failed": "FAILED",
            "error": "FAILED",
        }.get(state_raw, "IDLE")
        return _tile(
            "imports",
            "Imports",
            mc_state,
            f"Last job: {state_raw or 'unknown'}.",
            actions=["Pause", "Resume"] if mc_state in ("WORKING", "PAUSED") else [],
        )
    except Exception:  # noqa: BLE001
        return _tile("imports", "Imports", "IDLE", "No import state available.")


def _webhooks_tile() -> dict:
    try:
        from apps.sync.models import WebhookReceipt

        recent_count = WebhookReceipt.objects.filter(
            created_at__gte=timezone.now() - timedelta(minutes=30)
        ).count()
        if recent_count == 0:
            return _tile(
                "webhooks",
                "Webhooks",
                "IDLE",
                "No receipts in last 30 min.",
            )
        return _tile(
            "webhooks",
            "Webhooks",
            "WORKING",
            f"{recent_count} receipts in last 30 min.",
        )
    except Exception:  # noqa: BLE001
        return _tile("webhooks", "Webhooks", "IDLE", "No webhook state available.")


def _read_datetime_setting(key: str):
    from datetime import datetime

    row = AppSetting.objects.filter(key=key).first()
    if row is None or not row.value:
        return None
    raw = str(row.value).strip().strip('"')
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            from django.utils.timezone import utc

            dt = dt.replace(tzinfo=utc)
        return dt
    except (ValueError, TypeError):
        return None


def _humanize_age(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < _SECONDS_PER_HOUR:
        return f"{s // 60}m ago"
    if s < _SECONDS_PER_DAY:
        return f"{s // _SECONDS_PER_HOUR}h ago"
    return f"{s // _SECONDS_PER_DAY}d ago"
