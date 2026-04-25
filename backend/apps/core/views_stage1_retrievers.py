"""Stage-1 retriever settings endpoint (Group C.1-C.3 wiring).

Exposes the two AppSetting flags that control whether the optional
Stage-1 retrievers participate in the candidate pool:

- ``stage1.lexical_retriever_enabled`` — Group C.2 (token-overlap
  ``LexicalRetriever`` + Stage-1.5 RRF fusion via pick #31).
- ``stage1.query_expansion_retriever_enabled`` — Group C.3 (Rocchio
  PRF ``QueryExpansionRetriever``, pick #27).

Both default off. When operators flip either on, the next pipeline
pass automatically uses the multi-retriever path with
:mod:`apps.pipeline.services.reciprocal_rank_fusion` to fuse the
ranked lists per destination — no other code change required.

The semantic retriever is always on (legacy default); it doesn't
appear here because there's nothing to toggle.

Mirrors the shape of ``views_fr099_fr105.py``: single REST view at
``/api/settings/stage1-retrievers/`` returning + accepting a flat
JSON object. Reuses the same ``_persist_settings`` /
``_read_setting`` helpers from ``views_antispam`` so the on-disk
shape matches every other settings group.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .views_antispam import _persist_settings, _read_setting


# ── Defaults + descriptions ──────────────────────────────────────


_SETTINGS_DEFAULTS: dict[str, bool] = {
    "lexical_retriever_enabled": False,
    "query_expansion_retriever_enabled": False,
}


_SETTINGS_DESCRIPTIONS: dict[str, str] = {
    "lexical_retriever_enabled": (
        "Group C.2: Adds the LexicalRetriever (token-overlap) to "
        "Stage-1. When ON, the candidate pool fuses semantic + "
        "lexical rankings via Reciprocal Rank Fusion (pick #31, "
        "Cormack et al. 2009 SIGIR). Useful when the operator "
        "expects literal-term-match queries."
    ),
    "query_expansion_retriever_enabled": (
        "Group C.3: Adds the QueryExpansionRetriever (Rocchio PRF, "
        "pick #27) on top of Stage-1. Surfaces hosts that share "
        "expansion terms (synonyms / related vocabulary) with the "
        "destination — even when they don't share the literal title "
        "tokens. Combine with the lexical retriever for the richest "
        "fused ranking."
    ),
}


# ── Read / write helpers ─────────────────────────────────────────


def _coerce_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return fallback


def get_stage1_retriever_settings() -> dict[str, bool]:
    """Read the two flags back as a flat ``{field: bool}`` dict."""
    out: dict[str, bool] = {}
    for field, default in _SETTINGS_DEFAULTS.items():
        out[field] = _read_setting(
            f"stage1.{field}",
            default=default,
            cast=lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"},
        )
    return out


# ── DRF view ─────────────────────────────────────────────────────


class Stage1RetrieverSettingsView(APIView):
    """GET / PUT for the Stage-1 retriever flags.

    Response shape::

        {
          "lexical_retriever_enabled": false,
          "query_expansion_retriever_enabled": false
        }

    PUT accepts the same shape (or any subset). Missing keys keep
    their current value. Each non-bool input is coerced via
    :func:`_coerce_bool` (string "true"/"yes"/"on" or bool True →
    True; everything else → False).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_stage1_retriever_settings())

    def put(self, request):
        current = get_stage1_retriever_settings()
        payload = request.data or {}
        validated: dict[str, bool] = {}
        for field, default in _SETTINGS_DEFAULTS.items():
            incoming = payload.get(field, current.get(field, default))
            validated[field] = _coerce_bool(
                incoming, bool(current.get(field, default))
            )
        _persist_settings(
            "stage1",
            validated,
            category="ranking",
            descriptions=_SETTINGS_DESCRIPTIONS,
        )
        return Response(validated)
