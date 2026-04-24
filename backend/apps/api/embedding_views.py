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
    "performance.profile_override",
]
_SECRET_KEYS = {"embedding.api_key"}


def _get_setting(key: str) -> str:
    from apps.core.models import AppSetting

    row = AppSetting.objects.filter(key=key).first()
    if row and row.value is not None:
        return str(row.value)
    return ""


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


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

    provider_name = _get_setting("embedding.provider") or "local"
    fallback = _get_setting("embedding.fallback_provider") or "local"

    try:
        from apps.pipeline.services.embedding_providers import get_provider

        provider = get_provider()
        dimension = int(getattr(provider, "dimension", 0))
        signature = str(getattr(provider, "signature", ""))
        model_name = getattr(provider, "model_name", "")
        max_tokens = int(getattr(provider, "max_tokens", 0))
    except Exception:
        dimension = 0
        signature = ""
        model_name = _get_setting("embedding.model")
        max_tokens = 0

    profile = detect_profile()
    batch_size = recommended_batch_size(dimension=dimension or 1024, profile=profile)

    first_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
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
    except Exception:
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
                "vram_gb": round(profile.vram_gb, 2),
                "has_cuda": profile.has_cuda,
                "recommended_batch_size": batch_size,
            },
            "coverage": {
                "total": total_items,
                "embedded": with_embedding,
                "pct": round(100.0 * with_embedding / total_items, 2) if total_items else 0.0,
            },
            "spend_this_month": spent_by_provider,
            "recommended_provider": _get_setting("embedding.recommended_provider"),
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def embedding_provider(request: Request) -> Response:
    """GET: current + available provider list. POST: switch provider."""
    if request.method == "GET":
        return Response(
            {
                "active": _get_setting("embedding.provider") or "local",
                "fallback": _get_setting("embedding.fallback_provider") or "local",
                "available": ["local", "openai", "gemini"],
            }
        )
    name = str(request.data.get("name") or "").strip().lower()
    if name not in ("local", "openai", "gemini"):
        return Response({"detail": "invalid provider"}, status=status.HTTP_400_BAD_REQUEST)

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
    name = str(request.data.get("provider") or "").strip().lower() or "local"
    from apps.pipeline.services.embedding_providers import get_provider

    # Temporarily swap the AppSetting so get_provider resolves to the tested one.
    from apps.core.models import AppSetting

    previous = _get_setting("embedding.provider") or "local"
    try:
        AppSetting.objects.update_or_create(
            key="embedding.provider", defaults={"value": name}
        )
        from apps.pipeline.services.embedding_providers import clear_cache

        clear_cache()
        provider = get_provider()
        provider.healthcheck()
        return Response({"ok": True, "provider": name, "signature": provider.signature})
    except Exception as exc:
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def embedding_bakeoff_run(request: Request) -> Response:
    """Trigger a bake-off run asynchronously."""
    from apps.pipeline.tasks_embedding_bakeoff import embedding_provider_bakeoff

    sample_size = int(request.data.get("sample_size") or 1000)
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
