"""Embeddings page backend endpoints (plan Part 8c, FR-235).

Exposes provider config, status, control, bake-off, and audit data to the
Angular sidenav "Embeddings" page. All endpoints are auth-protected via the
existing DRF middleware.

Budget / cost / API-key operations go through ``AppSetting`` so the Embeddings
UI becomes the single source of truth for switching and configuring providers.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.api.query_params import coerce_int


_PROVIDER_KEYS = ["embedding.provider", "embedding.fallback_provider"]
_PROVIDER_CONFIG_KEYS = [
    "embedding.model",
    "embedding.api_key",
    "embedding.api_base",
    "embedding.dimensions_override",
    "embedding.rate_limit_rpm",
    "embedding.rate_limit_tpm",
    "embedding.monthly_budget_usd",
    "embedding.timeout_seconds",
    "embedding.max_retries",
    "embedding.bakeoff_sample_size",
    "embedding.bakeoff_cost_cap_usd",
    "embedding.audit_resample_size",
    "embedding.audit_norm_tolerance",
    "embedding.audit_drift_threshold",
    "embedding.gate_enabled",
    "embedding.gate_quality_delta_threshold",
    "embedding.gate_noop_cosine_threshold",
    "embedding.gate_stability_threshold",
]
_SECRET_KEYS = {"embedding.api_key"}
_PROVIDER_SCORE_FIELDS = (
    "job_id",
    "provider",
    "signature",
    "sample_size",
    "mrr_at_10",
    "ndcg_at_10",
    "recall_at_10",
    "latency_ms_p50",
    "latency_ms_p95",
    "compared_to",
    "verdict",
    "p_value",
    "loss_count",
    "is_banned",
    "explanation",
    "created_at",
)


def _get_setting(key: str) -> str:
    """Group D consolidation (2026-04-28): now a thin wrapper over
    ``AppSetting.get_str``. Kept as a module-local helper so existing
    call sites stay untouched."""
    from apps.core.models import AppSetting

    return AppSetting.get_str(key, "")


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def _as_float(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _score_provider_row(row: dict) -> dict:
    return {
        "provider": row["provider"],
        "signature": row.get("signature") or "",
        "sample_size": int(row.get("sample_size") or 0),
        "mrr_at_10": _as_float(row.get("mrr_at_10")),
        "ndcg_at_10": _as_float(row.get("ndcg_at_10")),
        "recall_at_10": _as_float(row.get("recall_at_10")),
        "latency_ms_p50": _as_float(row.get("latency_ms_p50")),
        "latency_ms_p95": _as_float(row.get("latency_ms_p95")),
        "compared_to": row.get("compared_to") or "",
        "verdict": row.get("verdict") or "unknown",
        "p_value": _as_float(row.get("p_value")),
        "loss_count": int(row.get("loss_count") or 0),
        "is_banned": bool(row.get("is_banned")),
        "explanation": row.get("explanation") or "",
    }


def _group_provider_score_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        job_id = str(row.get("job_id") or "")
        if not job_id:
            continue
        group = grouped.setdefault(
            job_id,
            {
                "job_id": job_id,
                "created_at": row.get("created_at"),
                "providers": [],
            },
        )
        group["providers"].append(_score_provider_row(row))
    return list(grouped.values())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_status(request: Request) -> Response:
    """Current provider, progress, budget spent, hardware profile."""
    from django.db.models import Sum
    from django.utils import timezone

    from apps.pipeline.models import EmbeddingCostLedger
    from apps.pipeline.services.hardware_profile import (
        detect_profile,
        recommended_batch_size,
    )

    provider_name = _get_setting("embedding.provider") or "openai"
    fallback = _get_setting("embedding.fallback_provider") or "openai"

    try:
        from apps.pipeline.services.embedding_providers import get_provider

        provider = get_provider()
        dimension = int(getattr(provider, "dimension", 0))
        signature = str(getattr(provider, "signature", ""))
        model_name = getattr(provider, "model_name", "")
        max_tokens = int(getattr(provider, "max_tokens", 0))
    except Exception:  # noqa: BLE001  # /api/embedding/status is a status endpoint that must always respond — degrade to "no provider known" rather than 500 the page when the embedding provider is mid-rebuild or unavailable.
        dimension = 0
        signature = ""
        model_name = _get_setting("embedding.model")
        max_tokens = 0

    profile = detect_profile()
    batch_size = recommended_batch_size(dimension=dimension or 1024, profile=profile)

    first_of_month = timezone.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    spent_rows = (
        EmbeddingCostLedger.objects.filter(created_at__gte=first_of_month)
        .values("provider")
        .annotate(total=Sum("cost_usd"), tokens=Sum("tokens_input"))
    )
    spent_by_provider = [
        {
            "provider": r["provider"],
            "cost_usd": float(r["total"] or 0),
            "tokens": int(r["tokens"] or 0),
        }
        for r in spent_rows
    ]

    try:
        from apps.content.models import ContentItem

        total_items = ContentItem.objects.filter(is_deleted=False).count()
        with_embedding = ContentItem.objects.filter(
            is_deleted=False, embedding__isnull=False
        ).count()
    except Exception:  # noqa: BLE001  # Status endpoint: degrade to zeros rather than 500 the page if the ContentItem table is mid-migration / unavailable.
        total_items = 0
        with_embedding = 0

    return Response(
        {
            "active_provider": provider_name,
            "fallback_provider": fallback,
            "model_name": model_name,
            "signature": signature,
            "dimension": dimension,
            "max_tokens": max_tokens,
            "hardware": {
                "tier": profile.tier,
                "ram_gb": round(profile.ram_gb, 2),
                "cpu_cores": profile.cpu_cores,
                "recommended_batch_size": batch_size,
            },
            "coverage": {
                "total": total_items,
                "embedded": with_embedding,
                "pct": round(100.0 * with_embedding / total_items, 2)
                if total_items
                else 0.0,
            },
            "spend_this_month": spent_by_provider,
            "recommended_provider": _get_setting("embedding.recommended_provider"),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_hardware_profile(request: Request) -> Response:
    """Detected hardware tier plus recommended batch sizes for common dims.

    Dedicated endpoint per FR-233 contract. Status endpoint exposes a subset
    nested inside its response; this view returns the canonical shape for
    clients that only need hardware info.
    """
    from apps.pipeline.services.hardware_profile import (
        detect_profile,
        recommended_batch_size,
    )

    profile = detect_profile()
    batch_sizes = {
        str(dim): recommended_batch_size(dimension=dim, profile=profile)
        for dim in (1024, 1536, 3072)
    }
    return Response(
        {
            "tier": profile.tier,
            "ram_gb": round(profile.ram_gb, 2),
            "cpu_cores": profile.cpu_cores,
            "batch_sizes": batch_sizes,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def embedding_provider(request: Request) -> Response:
    """GET: current + available provider list. POST: switch provider."""
    if request.method == "GET":
        return Response(
            {
                "active": _get_setting("embedding.provider") or "openai",
                "fallback": _get_setting("embedding.fallback_provider") or "openai",
                "available": ["openai", "gemini"],
            }
        )
    name = str(request.data.get("name") or "").strip().lower()
    if name not in ("openai", "gemini"):
        return Response(
            {"detail": "invalid provider"}, status=status.HTTP_400_BAD_REQUEST
        )

    from apps.core.models import AppSetting
    from apps.pipeline.services.embedding_providers import clear_cache

    AppSetting.objects.update_or_create(
        key="embedding.provider", defaults={"value": name}
    )
    clear_cache()
    return Response({"active": name})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def embedding_settings(request: Request) -> Response:
    """GET: full config (API key masked). POST: bulk update allowed keys."""
    if request.method == "GET":
        out = {}
        for key in _PROVIDER_CONFIG_KEYS + _PROVIDER_KEYS:
            val = _get_setting(key)
            out[key] = _mask_secret(val) if key in _SECRET_KEYS else val
        return Response(out)

    from apps.core.models import AppSetting

    updates = request.data or {}
    for key, value in updates.items():
        if key not in _PROVIDER_CONFIG_KEYS + _PROVIDER_KEYS:
            continue
        if value is None:
            continue
        AppSetting.objects.update_or_create(
            key=key,
            defaults={"value": str(value)},
        )
    from apps.pipeline.services.embedding_providers import clear_cache

    clear_cache()
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_test_connection(request: Request) -> Response:
    """Verify the given provider's credentials via a one-token ``healthcheck``."""
    name = str(request.data.get("provider") or "").strip().lower() or "openai"
    from apps.pipeline.services.embedding_providers import get_provider

    # Temporarily swap the AppSetting so get_provider resolves to the tested one.
    from apps.core.models import AppSetting

    previous = _get_setting("embedding.provider") or "openai"
    try:
        AppSetting.objects.update_or_create(
            key="embedding.provider", defaults={"value": name}
        )
        from apps.pipeline.services.embedding_providers import clear_cache

        clear_cache()
        provider = get_provider()
        provider.healthcheck()
        return Response({"ok": True, "provider": name, "signature": provider.signature})
    except Exception as exc:  # noqa: BLE001  # Provider switch is user-initiated; surface ANY failure as a 400 with the message so the operator can act on it (auth issues, network errors, missing model files, etc.).
        return Response(
            {"ok": False, "provider": name, "error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    finally:
        AppSetting.objects.update_or_create(
            key="embedding.provider", defaults={"value": previous}
        )
        from apps.pipeline.services.embedding_providers import clear_cache

        clear_cache()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_bakeoff_results(request: Request) -> Response:
    """List recent bake-off results, newest first, capped at 50."""
    from apps.pipeline.models import EmbeddingBakeoffResult

    rows = EmbeddingBakeoffResult.objects.order_by("-created_at").values()[:50]
    return Response(list(rows))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_provider_eval_runs(request: Request) -> Response:
    """List recent provider score runs grouped by run identifier."""
    from apps.pipeline.models import EmbeddingBakeoffResult

    rows = list(
        EmbeddingBakeoffResult.objects.order_by("-created_at")
        .values(*_PROVIDER_SCORE_FIELDS)[:100]
    )
    return Response({"runs": _group_provider_score_rows(rows)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_provider_eval_run(request: Request) -> Response:
    """Start provider scoring only when the user confirms possible cost."""
    from apps.pipeline.tasks_embedding_bakeoff import embedding_provider_bakeoff

    if request.data.get("cost_confirmed") is not True:
        return Response(
            {"detail": "cost confirmation required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    sample_size = coerce_int(
        request.data.get("sample_size"),
        default=1000,
        min_value=1,
        max_value=200_000,
    )
    async_result = embedding_provider_bakeoff.delay(sample_size=sample_size)
    return Response({"task_id": async_result.id, "sample_size": sample_size})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_provider_unban(request: Request) -> Response:
    """Remove one provider from the bake-off ban list."""
    import json

    from apps.core.models import AppSetting

    provider = str(request.data.get("provider") or "").strip().lower()
    if provider not in ("openai", "gemini"):
        return Response(
            {"detail": "invalid provider"}, status=status.HTTP_400_BAD_REQUEST
        )
    raw_value = AppSetting.get_str("embedding.provider_bans_json", "[]")
    try:
        decoded = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        decoded = []
    if not isinstance(decoded, list):
        decoded = []
    remaining = sorted(
        item for item in {str(value).strip().lower() for value in decoded} if item
    )
    remaining = [item for item in remaining if item != provider]
    AppSetting.objects.update_or_create(
        key="embedding.provider_bans_json",
        defaults={"value": json.dumps(remaining)},
    )
    return Response({"provider": provider, "is_banned": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_bakeoff_run(request: Request) -> Response:
    """Trigger a bake-off run asynchronously."""
    from apps.pipeline.tasks_embedding_bakeoff import embedding_provider_bakeoff

    # Bug fix 2026-05-04: bare int() crashed with HTTP 500 on
    # `{"sample_size": "foo"}`. Routed through coerce_int + clamp so
    # an over-large request can't trigger an OOM during bake-off.
    sample_size = coerce_int(
        request.data.get("sample_size"),
        default=1000,
        min_value=1,
        max_value=200_000,
    )
    async_result = embedding_provider_bakeoff.delay(sample_size=sample_size)
    return Response({"task_id": async_result.id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_audit_run(request: Request) -> Response:
    """Trigger a manual audit run (bypasses the fortnight gate)."""
    from apps.pipeline.tasks_embedding_audit import embedding_accuracy_audit

    async_result = embedding_accuracy_audit.delay(fortnightly=False, force=True)
    return Response({"task_id": async_result.id})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def embedding_gate_decisions(request: Request) -> Response:
    """Last 100 quality-gate decisions for the Audit tab."""
    from apps.pipeline.models import EmbeddingGateDecision

    rows = EmbeddingGateDecision.objects.order_by("-created_at").values()[:100]
    return Response(list(rows))
