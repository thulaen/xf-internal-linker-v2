"""Anti-spam settings endpoints and defaults."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AppSetting
from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
)


def _read_setting(key: str, *, default, cast):
    row = AppSetting.objects.filter(key=key).first()
    if row is None:
        return default
    try:
        return cast(row.value)
    except (TypeError, ValueError):
        return default


DEFAULT_ANCHOR_DIVERSITY_SETTINGS = {
    "enabled": recommended_bool("anchor_diversity.enabled"),
    "ranking_weight": recommended_float("anchor_diversity.ranking_weight"),
    "min_history_count": recommended_int("anchor_diversity.min_history_count"),
    "max_exact_match_share": recommended_float(
        "anchor_diversity.max_exact_match_share"
    ),
    "max_exact_match_count": recommended_int("anchor_diversity.max_exact_match_count"),
    "hard_cap_enabled": recommended_bool("anchor_diversity.hard_cap_enabled"),
}

DEFAULT_KEYWORD_STUFFING_SETTINGS = {
    "enabled": recommended_bool("keyword_stuffing.enabled"),
    "ranking_weight": recommended_float("keyword_stuffing.ranking_weight"),
    "alpha": recommended_float("keyword_stuffing.alpha"),
    "tau": recommended_float("keyword_stuffing.tau"),
    "dirichlet_mu": recommended_int("keyword_stuffing.dirichlet_mu"),
    "top_k_stuff_terms": recommended_int("keyword_stuffing.top_k_stuff_terms"),
}

DEFAULT_LINK_FARM_SETTINGS = {
    "enabled": recommended_bool("link_farm.enabled"),
    "ranking_weight": recommended_float("link_farm.ranking_weight"),
    "min_scc_size": recommended_int("link_farm.min_scc_size"),
    "density_threshold": recommended_float("link_farm.density_threshold"),
    "lambda": recommended_float("link_farm.lambda"),
}


def get_anchor_diversity_settings() -> dict[str, object]:
    return {
        "enabled": _read_setting(
            "anchor_diversity.enabled",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["enabled"],
            cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
        ),
        "ranking_weight": _read_setting(
            "anchor_diversity.ranking_weight",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["ranking_weight"],
            cast=float,
        ),
        "min_history_count": _read_setting(
            "anchor_diversity.min_history_count",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["min_history_count"],
            cast=int,
        ),
        "max_exact_match_share": _read_setting(
            "anchor_diversity.max_exact_match_share",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["max_exact_match_share"],
            cast=float,
        ),
        "max_exact_match_count": _read_setting(
            "anchor_diversity.max_exact_match_count",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["max_exact_match_count"],
            cast=int,
        ),
        "hard_cap_enabled": _read_setting(
            "anchor_diversity.hard_cap_enabled",
            default=DEFAULT_ANCHOR_DIVERSITY_SETTINGS["hard_cap_enabled"],
            cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
        ),
    }


def get_keyword_stuffing_settings() -> dict[str, object]:
    return {
        "enabled": _read_setting(
            "keyword_stuffing.enabled",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["enabled"],
            cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
        ),
        "ranking_weight": _read_setting(
            "keyword_stuffing.ranking_weight",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["ranking_weight"],
            cast=float,
        ),
        "alpha": _read_setting(
            "keyword_stuffing.alpha",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["alpha"],
            cast=float,
        ),
        "tau": _read_setting(
            "keyword_stuffing.tau",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["tau"],
            cast=float,
        ),
        "dirichlet_mu": _read_setting(
            "keyword_stuffing.dirichlet_mu",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["dirichlet_mu"],
            cast=int,
        ),
        "top_k_stuff_terms": _read_setting(
            "keyword_stuffing.top_k_stuff_terms",
            default=DEFAULT_KEYWORD_STUFFING_SETTINGS["top_k_stuff_terms"],
            cast=int,
        ),
    }


def get_link_farm_settings() -> dict[str, object]:
    return {
        "enabled": _read_setting(
            "link_farm.enabled",
            default=DEFAULT_LINK_FARM_SETTINGS["enabled"],
            cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
        ),
        "ranking_weight": _read_setting(
            "link_farm.ranking_weight",
            default=DEFAULT_LINK_FARM_SETTINGS["ranking_weight"],
            cast=float,
        ),
        "min_scc_size": _read_setting(
            "link_farm.min_scc_size",
            default=DEFAULT_LINK_FARM_SETTINGS["min_scc_size"],
            cast=int,
        ),
        "density_threshold": _read_setting(
            "link_farm.density_threshold",
            default=DEFAULT_LINK_FARM_SETTINGS["density_threshold"],
            cast=float,
        ),
        "lambda": _read_setting(
            "link_farm.lambda",
            default=DEFAULT_LINK_FARM_SETTINGS["lambda"],
            cast=float,
        ),
    }


def _persist_settings(
    prefix: str,
    validated: dict[str, object],
    *,
    category: str,
    descriptions: dict[str, str],
) -> None:
    for key, value in validated.items():
        value_type = (
            "bool"
            if isinstance(value, bool)
            else "int"
            if isinstance(value, int) and not isinstance(value, bool)
            else "float"
        )
        AppSetting.objects.update_or_create(
            key=f"{prefix}.{key}",
            defaults={
                "value": str(value).lower() if isinstance(value, bool) else str(value),
                "value_type": value_type,
                "category": category,
                "description": descriptions[key],
                "is_secret": False,
            },
        )


def _validate_anchor_diversity_settings(
    payload: dict, current: dict[str, object]
) -> dict[str, object]:
    def _bool(key: str) -> bool:
        raw = payload.get(key, current[key])
        return (
            raw
            if isinstance(raw, bool)
            else str(raw).strip().lower() in {"1", "true", "yes", "on"}
        )

    def _int(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return int(current[key])

    def _float(key: str, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return float(current[key])

    return {
        "enabled": _bool("enabled"),
        "ranking_weight": _float("ranking_weight", 0.0, 0.25),
        "min_history_count": _int("min_history_count", 1, 50),
        "max_exact_match_share": _float("max_exact_match_share", 0.05, 1.0),
        "max_exact_match_count": _int("max_exact_match_count", 1, 50),
        "hard_cap_enabled": _bool("hard_cap_enabled"),
    }


def _validate_keyword_stuffing_settings(
    payload: dict, current: dict[str, object]
) -> dict[str, object]:
    def _bool(key: str) -> bool:
        raw = payload.get(key, current[key])
        return (
            raw
            if isinstance(raw, bool)
            else str(raw).strip().lower() in {"1", "true", "yes", "on"}
        )

    def _int(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return int(current[key])

    def _float(key: str, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return float(current[key])

    return {
        "enabled": _bool("enabled"),
        "ranking_weight": _float("ranking_weight", 0.0, 0.25),
        "alpha": _float("alpha", 0.1, 20.0),
        "tau": _float("tau", 0.0, 2.0),
        "dirichlet_mu": _int("dirichlet_mu", 100, 20000),
        "top_k_stuff_terms": _int("top_k_stuff_terms", 1, 20),
    }


def _validate_link_farm_settings(
    payload: dict, current: dict[str, object]
) -> dict[str, object]:
    def _bool(key: str) -> bool:
        raw = payload.get(key, current[key])
        return (
            raw
            if isinstance(raw, bool)
            else str(raw).strip().lower() in {"1", "true", "yes", "on"}
        )

    def _int(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return int(current[key])

    def _float(key: str, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(payload.get(key, current[key]))))
        except (TypeError, ValueError):
            return float(current[key])

    return {
        "enabled": _bool("enabled"),
        "ranking_weight": _float("ranking_weight", 0.0, 0.25),
        "min_scc_size": _int("min_scc_size", 2, 100),
        "density_threshold": _float("density_threshold", 0.1, 1.0),
        "lambda": _float("lambda", 0.01, 5.0),
    }


class AnchorDiversitySettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_anchor_diversity_settings())

    def put(self, request):
        current = get_anchor_diversity_settings()
        validated = _validate_anchor_diversity_settings(request.data or {}, current)
        _persist_settings(
            "anchor_diversity",
            validated,
            category="anchor",
            descriptions={
                "enabled": "Whether FR-045 anchor diversity scoring is active.",
                "ranking_weight": "Penalty weight for exact-match anchor reuse.",
                "min_history_count": "Minimum active suggestion history rows before reuse scoring activates.",
                "max_exact_match_share": "Maximum safe exact-match share before FR-045 penalises the candidate.",
                "max_exact_match_count": "Maximum safe exact-match count before FR-045 penalises the candidate.",
                "hard_cap_enabled": "Whether FR-045 may hard-block extreme exact-match reuse instead of only demoting it.",
            },
        )
        return Response(validated)


class KeywordStuffingSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_keyword_stuffing_settings())

    def put(self, request):
        current = get_keyword_stuffing_settings()
        validated = _validate_keyword_stuffing_settings(request.data or {}, current)
        _persist_settings(
            "keyword_stuffing",
            validated,
            category="ml",
            descriptions={
                "enabled": "Whether FR-198 keyword stuffing scoring is active.",
                "ranking_weight": "Penalty weight for keyword stuffing anomalies.",
                "alpha": "Sigmoid steepness for FR-198 stuffing penalty.",
                "tau": "Neutral-to-penalised decision threshold for FR-198.",
                "dirichlet_mu": "Dirichlet smoothing mass for the corpus baseline language model.",
                "top_k_stuff_terms": "How many high-risk repeated terms to surface in diagnostics.",
            },
        )
        return Response(validated)


class LinkFarmSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_link_farm_settings())

    def put(self, request):
        current = get_link_farm_settings()
        validated = _validate_link_farm_settings(request.data or {}, current)
        _persist_settings(
            "link_farm",
            validated,
            category="ml",
            descriptions={
                "enabled": "Whether FR-197 link-farm ring scoring is active.",
                "ranking_weight": "Penalty weight for reciprocal ring topology.",
                "min_scc_size": "Minimum SCC size before FR-197 considers a reciprocal ring suspicious.",
                "density_threshold": "Density floor used by the reciprocal ring detector.",
                "lambda": "Penalty-curve slope for FR-197 ring scoring.",
            },
        )
        return Response(validated)
