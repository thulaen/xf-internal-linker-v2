"""FR-099 through FR-105 ranking-signal settings endpoint.

Single REST view exposing the 25 AppSetting keys for all 7
graph-topology signals (DARB, KMIG, TAPB, KCIB, BERP, HGTE, RSQVA) under
one URL: ``/api/settings/fr099-fr105/``.

Groups the 7 signals in one endpoint rather than 7 separate views because
they were shipped as one logical slice in the FR-099..FR-105 plan
(2026-04-24) — the frontend renders them as 7 cards but saves them
together. Backend persistence uses the existing ``AppSetting`` table
and the ``_persist_settings`` helper from ``views_antispam`` so the data
shape matches every other signal's on-disk format.

Gate A compliance: every default value is baseline-cited in the
matching spec ``docs/specs/fr099-*.md`` through ``fr105-*.md``.
See ``docs/RANKING-GATES.md`` for the governance context.
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

from .views_antispam import _persist_settings, _read_setting


# ── Defaults + grouped config ────────────────────────────────────────

_SIGNAL_DEFAULTS: dict[str, dict[str, object]] = {
    "darb": {
        "enabled": recommended_bool("darb.enabled"),
        "ranking_weight": recommended_float("darb.ranking_weight"),
        "out_degree_saturation": recommended_int("darb.out_degree_saturation"),
        "min_host_value": recommended_float("darb.min_host_value"),
    },
    "kmig": {
        "enabled": recommended_bool("kmig.enabled"),
        "ranking_weight": recommended_float("kmig.ranking_weight"),
        "attenuation": recommended_float("kmig.attenuation"),
        "max_hops": recommended_int("kmig.max_hops"),
    },
    "tapb": {
        "enabled": recommended_bool("tapb.enabled"),
        "ranking_weight": recommended_float("tapb.ranking_weight"),
        "apply_to_articulation_node_only": recommended_bool(
            "tapb.apply_to_articulation_node_only"
        ),
    },
    "kcib": {
        "enabled": recommended_bool("kcib.enabled"),
        "ranking_weight": recommended_float("kcib.ranking_weight"),
        "min_kcore_spread": recommended_int("kcib.min_kcore_spread"),
    },
    "berp": {
        "enabled": recommended_bool("berp.enabled"),
        "ranking_weight": recommended_float("berp.ranking_weight"),
        "min_component_size": recommended_int("berp.min_component_size"),
    },
    "hgte": {
        "enabled": recommended_bool("hgte.enabled"),
        "ranking_weight": recommended_float("hgte.ranking_weight"),
        "min_host_out_degree": recommended_int("hgte.min_host_out_degree"),
    },
    "rsqva": {
        "enabled": recommended_bool("rsqva.enabled"),
        "ranking_weight": recommended_float("rsqva.ranking_weight"),
        "min_queries_per_page": recommended_int("rsqva.min_queries_per_page"),
        "min_query_clicks": recommended_int("rsqva.min_query_clicks"),
        "max_vocab_size": recommended_int("rsqva.max_vocab_size"),
    },
}


# Per-signal descriptions stored alongside AppSetting rows. Kept here
# (not in spec files) because _persist_settings writes them into the DB
# for the Settings admin UI.
_SIGNAL_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "darb": {
        "enabled": "FR-099 DARB (Dangling Authority Redistribution Bonus) master switch.",
        "ranking_weight": "FR-099 DARB ranking weight. Baseline: Page et al. 1999 §3.2 eq. 1.",
        "out_degree_saturation": "FR-099 DARB out-degree above which a host is no longer 'dangling'. Baseline: Broder et al. 2000 Table 1 median=8.",
        "min_host_value": "FR-099 DARB minimum content_value_score threshold. Below this, signal stays neutral.",
    },
    "kmig": {
        "enabled": "FR-100 KMIG (Katz Marginal Information Gain) master switch.",
        "ranking_weight": "FR-100 KMIG ranking weight. Baseline: Katz 1953 Psychometrika 18(1) §2 eq. 2.",
        "attenuation": "FR-100 KMIG Katz β attenuation factor. Pigueiral 2017 truncated-Katz default.",
        "max_hops": "FR-100 KMIG max Katz path length. Truncate at 2 for RAM budget.",
    },
    "tapb": {
        "enabled": "FR-101 TAPB (Tarjan Articulation Point Boost) master switch.",
        "ranking_weight": "FR-101 TAPB ranking weight. Baseline: Tarjan 1972 SIAM §3.",
        "apply_to_articulation_node_only": "FR-101 TAPB strict AP gate. Off widens to graded nearness (future).",
    },
    "kcib": {
        "enabled": "FR-102 KCIB (K-Core Integration Boost) master switch.",
        "ranking_weight": "FR-102 KCIB ranking weight. Baseline: Seidman 1983 Social Networks 5(3) §2.",
        "min_kcore_spread": "FR-102 KCIB minimum host.kcore - dest.kcore delta.",
    },
    "berp": {
        "enabled": "FR-103 BERP (Bridge-Edge Redundancy Penalty) master switch.",
        "ranking_weight": "FR-103 BERP penalty weight. Baseline: Hopcroft-Tarjan 1973 CACM 16(6) §2.",
        "min_component_size": "FR-103 BERP minimum BCC size before penalty applies.",
    },
    "hgte": {
        "enabled": "FR-104 HGTE (Host-Graph Topic Entropy Boost) master switch.",
        "ranking_weight": "FR-104 HGTE ranking weight. Baseline: Shannon 1948 BSTJ 27(3) §6 eq. 4.",
        "min_host_out_degree": "FR-104 HGTE minimum host out-degree before entropy is meaningful.",
    },
    "rsqva": {
        "enabled": "FR-105 RSQVA (Reverse Search-Query Vocabulary Alignment) master switch.",
        "ranking_weight": "FR-105 RSQVA ranking weight. Baseline: Salton & Buckley 1988 IP&M 24(5) §3-4.",
        "min_queries_per_page": "FR-105 RSQVA minimum GSC queries per page before vector is built.",
        "min_query_clicks": "FR-105 RSQVA minimum clicks a query needs to count.",
        "max_vocab_size": "FR-105 RSQVA cap on distinct query terms per page.",
    },
}


# ── Read / write helpers ─────────────────────────────────────────────


def get_fr099_fr105_settings() -> dict[str, dict[str, object]]:
    """Read the 25 AppSetting keys back as a {signal: {field: value}} tree."""
    result: dict[str, dict[str, object]] = {}
    for signal, fields in _SIGNAL_DEFAULTS.items():
        group: dict[str, object] = {}
        for field, default in fields.items():
            key = f"{signal}.{field}"
            if isinstance(default, bool):
                group[field] = _read_setting(
                    key,
                    default=default,
                    cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
                )
            elif isinstance(default, int):
                group[field] = _read_setting(key, default=default, cast=int)
            else:
                group[field] = _read_setting(key, default=default, cast=float)
        result[signal] = group
    return result


# ── Validation ───────────────────────────────────────────────────────


_RANGE_FLOAT_0_1 = (0.0, 1.0)
_RANGE_WEIGHT = (0.0, 0.25)


def _clamp_float(value, lo: float, hi: float, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if v != v:  # NaN
        return fallback
    return max(lo, min(hi, v))


def _clamp_int(value, lo: int, hi: int, fallback: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, v))


def _coerce_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return fallback


def _validate_signal_group(
    signal: str, payload: dict, current: dict
) -> dict[str, object]:
    """Clamp each field to a safe range; fall back to current value on invalid input."""
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
        elif field == "attenuation":
            out[field] = _clamp_float(
                incoming, 0.1, 0.9, float(current.get(field, default_value))
            )
        elif field == "min_host_value":
            out[field] = _clamp_float(
                incoming, 0.0, 1.0, float(current.get(field, default_value))
            )
        elif isinstance(default_value, int):
            # Loose but defensive int bounds covering all FR-099..105 int fields.
            out[field] = _clamp_int(
                incoming, 1, 100000, int(current.get(field, default_value))
            )
        else:
            out[field] = _clamp_float(
                incoming, 0.0, 1.0, float(current.get(field, default_value))
            )
    return out


# ── DRF view ─────────────────────────────────────────────────────────


class FR099FR105SettingsView(APIView):
    """GET/PUT for all 7 FR-099..105 signal settings in one request.

    Response shape::

        {
          "darb":  {"enabled": true, "ranking_weight": 0.04, ...},
          "kmig":  {"enabled": true, "ranking_weight": 0.05, ...},
          "tapb":  {...},
          "kcib":  {...},
          "berp":  {...},
          "hgte":  {...},
          "rsqva": {...}
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_fr099_fr105_settings())

    def put(self, request):
        current = get_fr099_fr105_settings()
        payload = request.data or {}
        validated: dict[str, dict[str, object]] = {}
        for signal in _SIGNAL_DEFAULTS:
            incoming = payload.get(signal) or {}
            validated[signal] = _validate_signal_group(signal, incoming, current[signal])

        for signal, fields in validated.items():
            _persist_settings(
                signal,
                fields,
                category="ranking",
                descriptions=_SIGNAL_DESCRIPTIONS[signal],
            )
        return Response(validated)
