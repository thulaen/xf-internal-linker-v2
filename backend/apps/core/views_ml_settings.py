"""
ML feature settings and triggers views extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import logging
import uuid

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import coerce_bool
from apps.api.throttles import (
    ChallengerEvalThrottle as _ChallengerEvalThrottle,
    GraphRebuildThrottle as _GraphRebuildThrottle,
    WeightRecalcThrottle as _WeightRecalcThrottle,
)
from apps.core.services.settings_helpers import (
    coerce_clamp_float,
    coerce_clamp_int,
    coerce_lenient_bool,
    read_app_setting_int,
)
from apps.core.views_settings import _format_setting_value

logger = logging.getLogger(__name__)


class ClickDistanceSettingsView(APIView):
    """GET/PUT /api/settings/click-distance/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_click_distance_settings
        return Response(get_click_distance_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_click_distance_settings,
            get_click_distance_settings,
        )

        current = get_click_distance_settings()
        try:
            validated = _validate_click_distance_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, value in validated.items():
            AppSetting.objects.update_or_create(
                key=f"click_distance.{key}", defaults={"value": str(value)}
            )
        return Response(validated)


class ClickDistanceRecalculateView(APIView):
    """POST /api/settings/click-distance/recalculate/"""
    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import recalculate_click_distance_task
        task = recalculate_click_distance_task.delay()
        return Response({"status": "queued", "job_id": task.id})


class FeedbackRerankSettingsView(APIView):
    """GET/PUT /api/settings/explore-exploit/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_feedback_rerank_settings
        return Response(get_feedback_rerank_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_feedback_rerank_settings,
            get_feedback_rerank_settings,
        )

        current = get_feedback_rerank_settings()
        try:
            validated = _validate_feedback_rerank_settings(
                request.data, current=current
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "explore_exploit.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether feedback-driven explore/exploit reranking is active.",
            },
            "explore_exploit.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Multiplier weight for the feedback-driven score component.",
            },
            "explore_exploit.exploration_rate": {
                "value": str(validated["exploration_rate"]),
                "value_type": "float",
                "description": "k factor for the UCB1 exploration boost.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class ClusteringSettingsView(APIView):
    """GET/PUT /api/settings/clustering/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_clustering_settings
        return Response(get_clustering_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_clustering_settings,
            get_clustering_settings,
        )

        current = get_clustering_settings()
        try:
            validated = _validate_clustering_settings(request.data, current)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "clustering.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether to cluster near-duplicate destinations and suppress non-canonicals.",
            },
            "clustering.similarity_threshold": {
                "value": str(validated["similarity_threshold"]),
                "value_type": "float",
                "description": "Cosine distance threshold for near-duplicate grouping (lower = stricter).",
            },
            "clustering.suppression_penalty": {
                "value": str(validated["suppression_penalty"]),
                "value_type": "float",
                "description": "Fixed score penalty applied to non-canonical cluster members.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class ClusteringRecalculateView(APIView):
    """POST /api/settings/clustering/recalculate/"""
    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import run_clustering_pass
        job_id = str(uuid.uuid4())
        run_clustering_pass.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


def _validate_slate_diversity_settings(payload: dict, current: dict) -> dict:
    """Validate and clamp slate diversity settings."""
    from apps.core.services.settings_helpers import DEFAULT_SLATE_DIVERSITY_SETTINGS

    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, DEFAULT_SLATE_DIVERSITY_SETTINGS[key]))

    def _get_bool(key: str) -> bool:
        val = payload.get(key, current.get(key))
        return coerce_bool(val, default=False)

    return {
        "enabled": _get_bool("enabled"),
        "diversity_lambda": max(0.0, min(1.0, _get_float("diversity_lambda"))),
        "score_window": max(0.05, min(1.0, _get_float("score_window"))),
        "similarity_cap": max(0.70, min(0.99, _get_float("similarity_cap"))),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }


class SlateDiversitySettingsView(APIView):
    """GET/PUT /api/settings/slate-diversity/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_slate_diversity_settings
        return Response(get_slate_diversity_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_slate_diversity_settings

        current = get_slate_diversity_settings()
        try:
            validated = _validate_slate_diversity_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "slate_diversity.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-015 MMR slate diversity reranking is active.",
            },
            "slate_diversity.diversity_lambda": {
                "value": str(validated["diversity_lambda"]),
                "value_type": "float",
                "description": "MMR lambda: 1.0 = pure relevance, 0.0 = pure diversity.",
            },
            "slate_diversity.score_window": {
                "value": str(validated["score_window"]),
                "value_type": "float",
                "description": "Max score gap from top candidate for MMR eligibility.",
            },
            "slate_diversity.similarity_cap": {
                "value": str(validated["similarity_cap"]),
                "value_type": "float",
                "description": "Cosine similarity above which two destinations are flagged as redundant.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightTuneTriggerView(APIView):
    """POST /api/settings/weight-tune/trigger/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.pipeline.tasks import monthly_weight_tune
        task = monthly_weight_tune.delay()
        return Response(
            {"detail": "Weight-tune task queued.", "task_id": task.id}, status=202
        )


class ChallengerEvaluateView(APIView):
    """POST /api/settings/weight-tune/evaluate/<run_id>/"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [_ChallengerEvalThrottle]

    def post(self, request, run_id):
        from apps.pipeline.tasks import evaluate_weight_challenger
        from apps.suggestions.models import RankingChallenger

        if not RankingChallenger.objects.filter(
            run_id=run_id, status="pending"
        ).exists():
            return Response(
                {"detail": f"No pending challenger with run_id '{run_id}'."},
                status=404,
            )

        task = evaluate_weight_challenger.delay(run_id=run_id)
        return Response(
            {"detail": "Evaluation queued.", "task_id": task.id}, status=202
        )


# ── Graph-candidate row spec, validator, and view ────────────────


_GRAPH_CANDIDATE_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "enabled",
        "graph_candidate.enabled",
        "bool",
        "Whether FR-021 Pixie walk candidate generation is active.",
    ),
    (
        "walk_steps_per_entity",
        "graph_candidate.walk_steps_per_entity",
        "int",
        "Number of Pixie random walk steps to perform per query entity.",
    ),
    (
        "min_stable_candidates",
        "graph_candidate.min_stable_candidates",
        "int",
        "Minimum number of stable candidates to find before early stopping.",
    ),
    (
        "min_visit_threshold",
        "graph_candidate.min_visit_threshold",
        "int",
        "Minimum walk visits required for a node to be considered stable.",
    ),
    (
        "top_k_candidates",
        "graph_candidate.top_k_candidates",
        "int",
        "Max number of top-visited candidates to return to the pipeline.",
    ),
    (
        "top_n_entities_per_article",
        "graph_candidate.top_n_entities_per_article",
        "int",
        "Max number of top entities to extract per article for graph linking.",
    ),
)


def _build_graph_candidate_rows(validated: dict) -> dict[str, dict]:
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _GRAPH_CANDIDATE_ROW_SPEC
    }


_GRAPH_CANDIDATE_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "walk_steps_per_entity": (10, 10000),
    "min_stable_candidates": (5, 500),
    "min_visit_threshold": (1, 20),
    "top_k_candidates": (10, 1000),
    "top_n_entities_per_article": (1, 100),
}


def _validate_graph_candidate_settings(payload: dict, current: dict) -> dict:
    out: dict = {"enabled": coerce_lenient_bool(payload, current, "enabled")}
    for key, (lo, hi) in _GRAPH_CANDIDATE_INT_BOUNDS.items():
        out[key] = coerce_clamp_int(payload, current, key, lo, hi)
    return out


class GraphCandidateSettingsView(APIView):
    """GET/PUT /api/settings/graph-candidate/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_graph_candidate_settings
        return Response(get_graph_candidate_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_graph_candidate_settings

        current = get_graph_candidate_settings()
        try:
            validated = _validate_graph_candidate_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, row in _build_graph_candidate_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


# ── Value-model row builders, bounds, validator, view ────────────


def _vm_bool_str(v: object) -> str:
    return "true" if v else "false"


def _build_value_model_rows(validated: dict) -> dict[str, dict[str, str]]:
    return {
        **_vm_rows_core(validated),
        **_vm_rows_engagement(validated),
        **_vm_rows_hot_decay(validated),
        **_vm_rows_co_occurrence(validated),
    }


def _vm_rows_core(validated: dict) -> dict[str, dict[str, str]]:
    return {
        "value_model.enabled": {
            "value": _vm_bool_str(validated["enabled"]),
            "value_type": "bool",
            "description": "Whether FR-021 Instagram-style value pre-scoring is active.",
        },
        "value_model.w_relevance": {
            "value": str(validated["w_relevance"]),
            "value_type": "float",
            "description": "Value component weight: semantic relevance.",
        },
        "value_model.w_traffic": {
            "value": str(validated["w_traffic"]),
            "value_type": "float",
            "description": "Value component weight: historical traffic.",
        },
        "value_model.w_freshness": {
            "value": str(validated["w_freshness"]),
            "value_type": "float",
            "description": "Value component weight: content freshness.",
        },
        "value_model.w_authority": {
            "value": str(validated["w_authority"]),
            "value_type": "float",
            "description": "Value component weight: content authority.",
        },
        "value_model.w_penalty": {
            "value": str(validated["w_penalty"]),
            "value_type": "float",
            "description": "Value component weight: blocklist/penalty sink.",
        },
        "value_model.traffic_lookback_days": {
            "value": str(validated["traffic_lookback_days"]),
            "value_type": "int",
            "description": "Number of days of traffic history to look back.",
        },
        "value_model.traffic_fallback_value": {
            "value": str(validated["traffic_fallback_value"]),
            "value_type": "float",
            "description": "Default traffic score to use if no data exists.",
        },
    }


def _vm_rows_engagement(validated: dict) -> dict[str, dict[str, str]]:
    return {
        "value_model.engagement_signal_enabled": {
            "value": _vm_bool_str(validated["engagement_signal_enabled"]),
            "value_type": "bool",
            "description": "Whether FR-024 engagement (read-through rate) signal is active.",
        },
        "value_model.w_engagement": {
            "value": str(validated["w_engagement"]),
            "value_type": "float",
            "description": "Value component weight: engagement / read-through rate signal.",
        },
        "value_model.engagement_lookback_days": {
            "value": str(validated["engagement_lookback_days"]),
            "value_type": "int",
            "description": "Rolling window (days) for averaging SearchMetric engagement rows.",
        },
        "value_model.engagement_words_per_minute": {
            "value": str(validated["engagement_words_per_minute"]),
            "value_type": "int",
            "description": "WPM constant used to estimate article read time.",
        },
        "value_model.engagement_cap_ratio": {
            "value": str(validated["engagement_cap_ratio"]),
            "value_type": "float",
            "description": "Cap applied to raw read-through rate before site-wide normalization.",
        },
        "value_model.engagement_fallback_value": {
            "value": str(validated["engagement_fallback_value"]),
            "value_type": "float",
            "description": "Fallback signal value when no SearchMetric rows exist for a destination.",
        },
    }


def _vm_rows_hot_decay(validated: dict) -> dict[str, dict[str, str]]:
    return {
        "value_model.hot_decay_enabled": {
            "value": _vm_bool_str(validated["hot_decay_enabled"]),
            "value_type": "bool",
            "description": "Whether FR-023 Reddit Hot decay replaces flat traffic averaging.",
        },
        "value_model.hot_gravity": {
            "value": str(validated["hot_gravity"]),
            "value_type": "float",
            "description": "Time-decay gravity factor for the Reddit Hot formula.",
        },
        "value_model.hot_clicks_weight": {
            "value": str(validated["hot_clicks_weight"]),
            "value_type": "float",
            "description": "Weight applied to click volume in hot score calculation.",
        },
        "value_model.hot_impressions_weight": {
            "value": str(validated["hot_impressions_weight"]),
            "value_type": "float",
            "description": "Weight applied to impression volume in hot score calculation.",
        },
        "value_model.hot_lookback_days": {
            "value": str(validated["hot_lookback_days"]),
            "value_type": "int",
            "description": "Number of days of daily traffic data to feed into hot scoring.",
        },
    }


def _vm_rows_co_occurrence(validated: dict) -> dict[str, dict[str, str]]:
    return {
        "value_model.co_occurrence_signal_enabled": {
            "value": _vm_bool_str(validated["co_occurrence_signal_enabled"]),
            "value_type": "bool",
            "description": "Whether the FR-025 session co-occurrence signal is active.",
        },
        "value_model.w_cooccurrence": {
            "value": str(validated["w_cooccurrence"]),
            "value_type": "float",
            "description": "Value component weight: session co-occurrence signal.",
        },
        "value_model.co_occurrence_fallback_value": {
            "value": str(validated["co_occurrence_fallback_value"]),
            "value_type": "float",
            "description": "Fallback signal value when no co-occurrence pair exists.",
        },
        "value_model.co_occurrence_min_co_sessions": {
            "value": str(validated["co_occurrence_min_co_sessions"]),
            "value_type": "int",
            "description": "Minimum co-session count for a pair to be used in scoring.",
        },
    }


_VALUE_MODEL_FLOAT_BOUNDS: dict[str, tuple[float, float]] = {
    "w_relevance": (0.0, 1.0),
    "w_traffic": (0.0, 1.0),
    "w_freshness": (0.0, 1.0),
    "w_authority": (0.0, 1.0),
    "w_penalty": (0.0, 1.0),
    "traffic_fallback_value": (0.0, 1.0),
    "w_engagement": (0.0, 1.0),
    "engagement_cap_ratio": (1.0, 5.0),
    "engagement_fallback_value": (0.0, 1.0),
    "hot_gravity": (0.001, 0.5),
    "hot_clicks_weight": (0.0, 5.0),
    "hot_impressions_weight": (0.0, 5.0),
    "w_cooccurrence": (0.0, 1.0),
    "co_occurrence_fallback_value": (0.0, 1.0),
}
_VALUE_MODEL_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "traffic_lookback_days": (1, 365),
    "engagement_lookback_days": (1, 365),
    "engagement_words_per_minute": (50, 600),
    "hot_lookback_days": (7, 365),
    "co_occurrence_min_co_sessions": (1, 100),
}
_VALUE_MODEL_BOOL_KEYS: tuple[str, ...] = (
    "enabled",
    "engagement_signal_enabled",
    "hot_decay_enabled",
    "co_occurrence_signal_enabled",
)


def _validate_value_model_settings(payload: dict, current: dict) -> dict:
    validated: dict = {
        key: coerce_lenient_bool(payload, current, key)
        for key in _VALUE_MODEL_BOOL_KEYS
    }
    for key, (lo, hi) in _VALUE_MODEL_FLOAT_BOUNDS.items():
        validated[key] = coerce_clamp_float(payload, current, key, lo, hi)
    for key, (lo_i, hi_i) in _VALUE_MODEL_INT_BOUNDS.items():
        validated[key] = coerce_clamp_int(payload, current, key, lo_i, hi_i)
    return validated


class ValueModelSettingsView(APIView):
    """GET/PUT /api/settings/value-model/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_value_model_settings
        return Response(get_value_model_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_value_model_settings

        current = get_value_model_settings()
        try:
            validated = _validate_value_model_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, row in _build_value_model_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


# ── Spam-guard defaults, accessor, validator, row builder, view ──


DEFAULT_SPAM_GUARD_SETTINGS: dict[str, int] = {
    "max_existing_links_per_host": 2,
    "max_anchor_words": 4,
    "paragraph_window": 3,
}

_SPAM_GUARD_KEYS = (
    "max_existing_links_per_host",
    "max_anchor_words",
    "paragraph_window",
)


def get_spam_guard_settings() -> dict[str, int]:
    return {
        key: read_app_setting_int(
            f"spam_guards.{key}",
            DEFAULT_SPAM_GUARD_SETTINGS[key],
        )
        for key in _SPAM_GUARD_KEYS
    }


def _validate_spam_guard_settings(payload: dict, current: dict) -> dict[str, int]:
    def _get_int(key: str, lo: int, hi: int) -> int:
        val = payload.get(key, current.get(key))
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return current.get(key, DEFAULT_SPAM_GUARD_SETTINGS[key])

    return {
        "max_existing_links_per_host": _get_int("max_existing_links_per_host", 1, 20),
        "max_anchor_words": _get_int("max_anchor_words", 1, 10),
        "paragraph_window": _get_int("paragraph_window", 1, 10),
    }


_SPAM_GUARD_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "max_existing_links_per_host",
        "spam_guards.max_existing_links_per_host",
        "int",
        "Maximum number of existing outgoing body links a host page may already carry "
        "(US9699123B2).",
    ),
    (
        "max_anchor_words",
        "spam_guards.max_anchor_words",
        "int",
        "Maximum number of words allowed in a suggested anchor phrase (US9699123B2).",
    ),
    (
        "paragraph_window",
        "spam_guards.paragraph_window",
        "int",
        "Sentence-position window for paragraph-cluster detection (US9699123B2).",
    ),
)


def _build_spam_guard_rows(validated: dict) -> dict[str, dict]:
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _SPAM_GUARD_ROW_SPEC
    }


class SpamGuardSettingsView(APIView):
    """GET/PUT /api/settings/spam-guards/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_spam_guard_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        current = get_spam_guard_settings()
        try:
            validated = _validate_spam_guard_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        for key, row in _build_spam_guard_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class GraphRebuildView(APIView):
    """POST /api/settings/graph/rebuild/"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [_GraphRebuildThrottle]

    def post(self, request):
        from apps.pipeline.tasks import dispatch_graph_rebuild
        job_id = str(uuid.uuid4())
        payload = dispatch_graph_rebuild(job_id=job_id)
        return Response(payload, status=202)
