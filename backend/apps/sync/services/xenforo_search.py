"""Read-only client for XenForo's ``/api/search/`` endpoint.

The XenForo Enhanced Search add-on transparently routes ``/api/search/``
calls to Elasticsearch. We treat ES as a read-only query layer reached
through the existing XenForo REST credentials — the same ``XF-Api-Key``
the importer already uses, the same rate-limit bucket, the same retry
contract.

Why a separate module from ``xenforo_api.py``: keeps the importer
(threads / posts / resources) independent of the search-specific shape
(``XFSearchHit`` typed return + search-only helpers like
``more_like_post``). Both modules share the same ``XenForoAPIClient._get``
helper for HTTP, rate limiting, and retries.

Reference
---------
- XenForo Enhanced Search docs: https://xenforo.com/docs/xf2/enhanced-search/
- BM25 (the keyword-match scoring formula): Robertson & Zaragoza (2009),
  "The Probabilistic Relevance Framework: BM25 and Beyond",
  *Foundations and Trends in IR* 3(4).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, NamedTuple, Optional

from apps.sync.services.xenforo_api import XenForoAPIClient

logger = logging.getLogger(__name__)


class XFSearchHit(NamedTuple):
    """One result row from a XenForo search.

    The forum returns a heterogeneous payload; this NamedTuple is the
    minimum stable shape downstream code (the BM25 retriever, the
    review-queue UI) can rely on. Unknown fields are dropped at parse
    time — callers that need them can always reach into ``raw``.
    """

    content_id: int
    """The XenForo origin ID — ``thread_id`` for thread hits, ``resource_id``
    for resource hits, ``post_id`` for post hits. Maps directly to
    ``ContentItem.content_id`` for the matching ``content_type``."""

    content_type: str
    """One of ``"thread"``, ``"post"``, ``"resource"``, or whatever the
    XF API echoes back. Aligned with ``ContentItem.CONTENT_TYPE_CHOICES``
    where possible; unrecognised values are passed through verbatim so a
    new XF content type added forum-side doesn't silently drop hits."""

    title: str
    """Display title of the hit (post title for posts, thread title for
    threads). Empty string if XF didn't return one."""

    snippet: str
    """Highlighted excerpt from XF's search response. Empty string if
    highlighting was disabled or the field was missing."""

    score: float
    """Raw BM25 score from Elasticsearch (or 0.0 when XF didn't include
    one). Not directly comparable across queries — RRF fusion uses
    rank, not score."""

    raw: Dict[str, Any]
    """The full hit dict as returned by XF, for callers that need a
    field this NamedTuple doesn't surface."""


class XenForoSearchClient:
    """Search-only companion to :class:`XenForoAPIClient`.

    Reuses the existing client for HTTP plumbing (rate limiting, retries,
    timeouts, auth header) — every search call shares the
    ``"xenforo_api"`` token bucket so the search retriever can never
    starve the importer or vice-versa.

    Three public methods cover the use cases planned in
    ``docs/specs/xf-bm25-retrieval.md``:

    - :meth:`search_threads` — keyword search over threads (returns one
      hit per matching thread, deduplicating multi-post matches forum-side).
      Used by the BM25 retriever's primary path.
    - :meth:`search_posts` — keyword search over individual posts. Used
      when the destination's anchor phrase is post-specific (rare).
    - :meth:`more_like_post` — XF's "more like this" query, returning
      threads/posts that share term overlap with the seed post. Used as
      a sanity-check signal in diagnostics.
    """

    SEARCH_ENDPOINT = "search/"

    def __init__(self, client: Optional[XenForoAPIClient] = None) -> None:
        self._client = client or XenForoAPIClient()

    @property
    def base_url(self) -> str:
        return self._client.base_url

    # ── Public search methods ──────────────────────────────────────

    def search_threads(self, query: str, *, limit: int = 200) -> List[XFSearchHit]:
        """Keyword-match threads whose title/body matches *query*.

        Returns up to *limit* hits ordered by XF's relevance score
        (BM25 when Enhanced Search is active). Empty list when the
        query is blank, when XF returns no matches, or when XF is
        unreachable (the underlying client logs the failure).
        """
        return self._search(query, search_type="thread", limit=limit)

    def search_posts(self, query: str, *, limit: int = 200) -> List[XFSearchHit]:
        """Keyword-match posts whose body matches *query*.

        Same contract as :meth:`search_threads` but at the post level.
        """
        return self._search(query, search_type="post", limit=limit)

    def more_like_post(
        self, post_id: int, *, limit: int = 200
    ) -> List[XFSearchHit]:
        """Return threads/posts XF considers similar to *post_id*.

        XF's MLT (more-like-this) implementation feeds the seed post's
        terms back into Elasticsearch's MLT query. Returns an empty
        list when the seed post is missing or XF is unreachable.
        """
        params = {"more_like": int(post_id), "limit": int(limit)}
        return self._invoke_and_parse(params)

    # ── Internals ──────────────────────────────────────────────────

    def _search(
        self, query: str, *, search_type: str, limit: int
    ) -> List[XFSearchHit]:
        if not query or not query.strip():
            return []
        if limit <= 0:
            return []
        params = {
            "q": query.strip(),
            "search_type": search_type,
            "limit": int(limit),
        }
        return self._invoke_and_parse(params)

    def _invoke_and_parse(self, params: Dict[str, Any]) -> List[XFSearchHit]:
        try:
            payload = self._client._get(  # noqa: SLF001 — intentional reuse of the shared HTTP helper
                self.SEARCH_ENDPOINT, params=params
            )
        except Exception as exc:  # noqa: BLE001 — surface as empty so a flaky search call cannot poison the pipeline
            logger.warning(
                "XenForo search failed (params=%s): %s — returning no hits",
                params,
                exc,
            )
            return []
        return self._parse_hits(payload)

    @staticmethod
    def _parse_hits(payload: Dict[str, Any]) -> List[XFSearchHit]:
        """Flatten XF's heterogeneous search payload into ``XFSearchHit``.

        XF 2.x returns ``{"results": [{"content_type": "...", "content": {...}}, ...]}``
        with the actual fields nested under ``content``. We tolerate
        flatter shapes too (some forks return ``{"results": [{...flat fields...}]}``)
        because the field names are the same either way.
        """
        results = payload.get("results") or payload.get("hits") or []
        if not isinstance(results, list):
            return []
        hits: List[XFSearchHit] = []
        for raw in results:
            if not isinstance(raw, dict):
                continue
            inner = raw.get("content") if isinstance(raw.get("content"), dict) else raw
            content_type = (
                raw.get("content_type")
                or inner.get("content_type")
                or _infer_type(inner)
            )
            if not content_type:
                continue
            content_id = _coerce_int(_pick_content_id(inner, content_type))
            if content_id is None:
                continue
            hits.append(
                XFSearchHit(
                    content_id=content_id,
                    content_type=str(content_type),
                    title=str(inner.get("title") or inner.get("thread_title") or ""),
                    snippet=str(
                        raw.get("snippet")
                        or inner.get("snippet")
                        or inner.get("highlight")
                        or ""
                    ),
                    score=_coerce_float(raw.get("score") or inner.get("score") or 0.0),
                    raw=raw,
                )
            )
        return hits


# ── Module-level helpers (pure, easy to unit-test) ─────────────────


def _coerce_int(value: Any) -> Optional[int]:
    """Best-effort int coercion that returns None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float:
    """Best-effort float coercion with a 0.0 fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _infer_type(inner: Dict[str, Any]) -> str:
    """Guess ``content_type`` from which ID field is present.

    Used as a fall-back when XF's payload omits the explicit
    ``content_type`` field (some older forks).
    """
    if "thread_id" in inner and "post_id" not in inner:
        return "thread"
    if "post_id" in inner:
        return "post"
    if "resource_id" in inner:
        return "resource"
    return ""


def _pick_content_id(inner: Dict[str, Any], content_type: str) -> Any:
    """Return the ID field that matches *content_type*.

    Prefers the type-specific field (``thread_id`` for threads, etc.)
    and falls back to a generic ``content_id`` if XF used that name.
    For thread-typed hits we deliberately favour ``thread_id`` even
    when ``post_id`` is also present, because the BM25 retriever wants
    to map back to the parent thread (which is what
    ``ContentItem.content_id`` stores for ``content_type="thread"``).
    """
    if content_type == "thread":
        return inner.get("thread_id") or inner.get("content_id")
    if content_type == "post":
        return inner.get("post_id") or inner.get("content_id")
    if content_type == "resource":
        return inner.get("resource_id") or inner.get("content_id")
    return inner.get("content_id")
