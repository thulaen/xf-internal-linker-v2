"""FR-260 through FR-265 ranking-signal settings endpoint.

Single REST view exposing the keys for all 6 advanced
graph-topology signals (TOSD, DSTP, ICPC, SBMA, RGSD, CSBR) under
one URL: ``/api/settings/advanced-graph-signals/``.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
)

from apps.api.query_params import coerce_bool, parse_bool_strict

from .views_antispam import _persist_settings, _read_setting


# ── Defaults + grouped config ────────────────────────────────────────

_SIGNAL_DEFAULTS: dict[str, dict[str, object]] = {
    "tosd": {
        "enabled": recommended_bool("tosd.enabled"),
        "ranking_weight": recommended_float("tosd.ranking_weight"),
        "filter_strength": recommended_float("tosd.filter_strength"),
    },
    "dstp": {
        "enabled": recommended_bool("dstp.enabled"),
        "ranking_weight": recommended_float("dstp.ranking_weight"),
        "smoothing_alpha": recommended_float("dstp.smoothing_alpha"),
    },
    "icpc": {
        "enabled": recommended_bool("icpc.enabled"),
        "ranking_weight": recommended_float("icpc.ranking_weight"),
        "min_community_size": recommended_int("icpc.min_community_size"),
    },
    "sbma": {
        "enabled": recommended_bool("sbma.enabled"),
        "ranking_weight": recommended_float("sbma.ranking_weight"),
        "num_blocks": recommended_int("sbma.num_blocks"),
    },
    "rgsd": {
        "enabled": recommended_bool("rgsd.enabled"),
        "ranking_weight": recommended_float("rgsd.ranking_weight"),
        "curvature_penalty": recommended_float("rgsd.curvature_penalty"),
    },
    "csbr": {
        "enabled": recommended_bool("csbr.enabled"),
        "ranking_weight": recommended_float("csbr.ranking_weight"),
        "min_overlap_threshold": recommended_float("csbr.min_overlap_threshold"),
    },
}

_SIGNAL_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "tosd": {
        "enabled": "FR-260 TOSD (Time-as-Operator Spectral Decay) master switch.",
        "ranking_weight": "FR-260 TOSD ranking weight.",
        "filter_strength": "FR-260 TOSD temporal filter strength.",
    },
    "dstp": {
        "enabled": "FR-261 DSTP (Directed Sequential Transition Probability) master switch.",
        "ranking_weight": "FR-261 DSTP ranking weight.",
        "smoothing_alpha": "FR-261 DSTP transition smoothing alpha.",
    },
    "icpc": {
        "enabled": "FR-262 ICPC (In-Community Popularity Contrast) master switch.",
        "ranking_weight": "FR-262 ICPC ranking weight.",
        "min_community_size": "FR-262 ICPC min community size.",
    },
    "sbma": {
        "enabled": "FR-263 SBMA (Stochastic Block Model Affinity) master switch.",
        "ranking_weight": "FR-263 SBMA ranking weight.",
        "num_blocks": "FR-263 SBMA number of topological blocks.",
    },
    "rgsd": {
        "enabled": "FR-264 RGSD (Riemannian Geodesic Semantic Distance) master switch.",
        "ranking_weight": "FR-264 RGSD ranking weight.",
        "curvature_penalty": "FR-264 RGSD curvature penalty.",
    },
    "csbr": {
        "enabled": "FR-265 CSBR (Cross-Silo Bridging Reward) master switch.",
        "ranking_weight": "FR-265 CSBR ranking weight.",
        "min_overlap_threshold": "FR-265 CSBR minimum overlap threshold.",
    },
}


def get_advanced_graph_signals_settings() -> dict[str, dict[str, object]]:
    """Read the keys back as a {signal: {field: value}} tree."""
    result: dict[str, dict[str, object]] = {}
    for signal, fields in _SIGNAL_DEFAULTS.items():
        group: dict[str, object] = {}
        for field, default in fields.items():
            key = f"{signal}.{field}"
            if isinstance(default, bool):
                group[field] = _read_setting(
                    key,
                    default=default,
                    cast=coerce_bool,
                )
            elif isinstance(default, int):
                group[field] = _read_setting(key, default=default, cast=int)
            else:
                group[field] = _read_setting(key, default=default, cast=float)
        result[signal] = group
    return result


_RANGE_FLOAT_0_1 = (0.0, 1.0)
_RANGE_WEIGHT = (0.0, 0.25)


def _clamp_float(value, lo: float, hi: float, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if v != v:
        return fallback
    return max(lo, min(hi, v))


def _clamp_int(value, lo: int, hi: int, fallback: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, v))


def _coerce_bool(value, fallback: bool) -> bool:
    return parse_bool_strict(value, default=fallback)


def _validate_signal_group(
    signal: str, payload: dict, current: dict
) -> dict[str, object]:
    out: dict[str, object] = {}
    defaults = _SIGNAL_DEFAULTS[signal]
    for field, default_value in defaults.items():
        incoming = payload.get(field, current.get(field, default_value))
        if isinstance(default_value, bool):
            out[field] = _coerce_bool(incoming, bool(current.get(field, default_value)))
        elif field == "ranking_weight":
            out[field] = _clamp_float(
                incoming,
                _RANGE_WEIGHT[0],
                _RANGE_WEIGHT[1],
                float(current.get(field, default_value)),
            )
        elif isinstance(default_value, int):
            out[field] = _clamp_int(
                incoming, 1, 100000, int(current.get(field, default_value))
            )
        else:
            # Handle float bounds per signal
            lo, hi = 0.0, 100.0  # general float range, adjust if needed
            out[field] = _clamp_float(
                incoming, lo, hi, float(current.get(field, default_value))
            )
    return out


class AdvancedGraphSignalsSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_advanced_graph_signals_settings())

    def put(self, request):
        current = get_advanced_graph_signals_settings()
        payload = request.data or {}
        validated: dict[str, dict[str, object]] = {}
        for signal in _SIGNAL_DEFAULTS:
            incoming = payload.get(signal) or {}
            validated[signal] = _validate_signal_group(
                signal, incoming, current[signal]
            )

        for signal, fields in validated.items():
            _persist_settings(
                signal,
                fields,
                category="ranking",
                descriptions=_SIGNAL_DESCRIPTIONS[signal],
            )
        return Response(validated)
