"""Stage-1 retriever settings endpoint (Group C.1-C.3 + XF-BM25 wiring).

Exposes the AppSetting flags that control whether optional Stage-1
retrievers participate in the candidate pool:

- ``stage1.lexical_retriever_enabled``: token-overlap ``LexicalRetriever``.
- ``stage1.query_expansion_retriever_enabled``: Rocchio query expansion.
- ``stage1.xenforo_bm25_retriever_enabled``: XenForo Enhanced Search
  BM25 over forum threads (Path A — REST API; see
  ``docs/specs/xf-bm25-retrieval.md``).

The lexical and XenForo-BM25 retrievers are seeded on by the Recommended
preset (migrations 0062 and 0066). Query expansion stays opt-in. When
operators flip any flag, the next pipeline pass uses the matching
retriever path and fuses ranked lists per destination via RRF.

The semantic retriever is always on and does not need a toggle here.
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import coerce_bool, parse_bool_strict

from .views_antispam import _persist_settings, _read_setting


# Defaults + descriptions
_SETTINGS_DEFAULTS: dict[str, bool] = {
    "lexical_retriever_enabled": True,
    "query_expansion_retriever_enabled": False,
    "xenforo_bm25_retriever_enabled": True,
    "tantivy_bm25_retriever_enabled": True,
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
        "destination, even when they do not share literal title tokens. "
        "Combine with the lexical retriever for the richest fused ranking."
    ),
    "xenforo_bm25_retriever_enabled": (
        "Adds the XenForoBM25Retriever (Path A — REST API). For each "
        "destination, queries XenForo's Enhanced Search "
        "(Elasticsearch-backed BM25, Robertson & Zaragoza 2009) via the "
        "existing API key, fused with FAISS results via RRF. XF-source "
        "candidates only — WordPress / blog / crawled hosts unaffected. "
        "See docs/specs/xf-bm25-retrieval.md."
    ),
    "tantivy_bm25_retriever_enabled": (
        "Adds the TantivyBM25Retriever: true BM25 keyword ranking "
        "(Robertson & Zaragoza 2009) over ALL host sources via Tantivy, "
        "the in-process Rust full-text index (approved JVM-free "
        "Lucene replacement — see "
        "docs/specs/fr-approved-library-expansion-bank.md). Builds its "
        "index in memory each pipeline pass from host titles, so it "
        "covers WordPress / blog / crawled hosts and keeps working when "
        "the forum's search endpoint is unavailable. Fused via RRF."
    ),
}


# Read / write helpers
def _coerce_bool(value, fallback: bool) -> bool:
    """Return a strict boolean, falling back when input is unknown."""
    return parse_bool_strict(value, default=fallback)


def get_stage1_retriever_settings() -> dict[str, bool]:
    """Read the three flags back as a flat ``{field: bool}`` dict."""
    out: dict[str, bool] = {}
    for field, default in _SETTINGS_DEFAULTS.items():
        out[field] = _read_setting(
            f"stage1.{field}",
            default=default,
            cast=coerce_bool,
        )
    return out


class Stage1RetrieverSettingsView(APIView):
    """GET / PUT for the Stage-1 retriever flags."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_stage1_retriever_settings())

    def put(self, request):
        current = get_stage1_retriever_settings()
        payload = request.data or {}
        validated: dict[str, bool] = {}
        for field, default in _SETTINGS_DEFAULTS.items():
            incoming = payload.get(field, current.get(field, default))
            validated[field] = _coerce_bool(incoming, bool(current.get(field, default)))
        _persist_settings(
            "stage1",
            validated,
            category="ranking",
            descriptions=_SETTINGS_DESCRIPTIONS,
        )
        return Response(validated)
