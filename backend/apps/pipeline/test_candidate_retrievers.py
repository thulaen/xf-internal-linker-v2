"""Tests for Group C.1 — Stage-1 list-of-retrievers refactor.

Verifies the abstraction in :mod:`apps.pipeline.services.candidate_retrievers`:

- ``SemanticRetriever`` produces the same output as the legacy single-
  function path (it wraps the same body).
- ``run_retrievers`` correctly unifies multiple retrievers' output
  with dedup-while-preserving-order.
- A failing retriever doesn't poison the others' contributions.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.candidate_retrievers import (
    RetrievalContext,
    SemanticRetriever,
    default_retrievers,
    run_retrievers,
)


def _make_context(
    destination_keys=None,
    dest_embeddings=None,
    content_records=None,
    content_to_sentence_ids=None,
    top_k: int = 5,
    block_size: int = 256,
) -> RetrievalContext:
    return RetrievalContext(
        destination_keys=destination_keys or (),
        dest_embeddings=(
            dest_embeddings
            if dest_embeddings is not None
            else np.zeros((0, 4), dtype=np.float32)
        ),
        content_records=content_records or {},
        content_to_sentence_ids=content_to_sentence_ids or {},
        top_k=top_k,
        block_size=block_size,
    )


class _FakeRetriever:
    """Test-only retriever returning a hard-coded mapping."""

    def __init__(self, name: str, mapping: dict):
        self.name = name
        self._mapping = mapping

    def retrieve(self, context: RetrievalContext) -> dict:
        return dict(self._mapping)


class _BoomRetriever:
    name = "boom"

    def retrieve(self, context: RetrievalContext) -> dict:
        raise RuntimeError("simulated retriever failure")


class DefaultRegistryTests(SimpleTestCase):
    def test_default_retrievers_contains_semantic(self) -> None:
        regs = default_retrievers()
        semantic = [retriever for retriever in regs if retriever.name == "semantic"]
        self.assertEqual(len(semantic), 1)
        self.assertIsInstance(semantic[0], SemanticRetriever)


class RunRetrieversTests(SimpleTestCase):
    def test_empty_registry_returns_empty_dict(self) -> None:
        result = run_retrievers([], context=_make_context())
        self.assertEqual(result, {})

    def test_single_retriever_passthrough(self) -> None:
        ret = _FakeRetriever("a", {("d1", "thread"): [10, 20, 30]})
        result = run_retrievers([ret], context=_make_context())
        self.assertEqual(result, {("d1", "thread"): [10, 20, 30]})

    def test_two_retrievers_unify_with_dedup_preserving_order(self) -> None:
        """fuse_with_rrf=False → C.1 dedup-preserving-order semantics."""
        ret_a = _FakeRetriever("a", {("d1", "thread"): [10, 20, 30]})
        ret_b = _FakeRetriever("b", {("d1", "thread"): [20, 40, 30, 50]})
        result = run_retrievers(
            [ret_a, ret_b], context=_make_context(), fuse_with_rrf=False
        )
        # Order: A's [10, 20, 30] first; then B contributes 40, 50
        # (already-seen 20 + 30 are dropped).
        self.assertEqual(result, {("d1", "thread"): [10, 20, 30, 40, 50]})

    def test_two_retrievers_default_uses_rrf_fusion(self) -> None:
        """Default fuse_with_rrf=True runs the RRF helper."""
        # Sentence ids: 10, 20, 30, 40, 50.
        # A ranks them [10, 20, 30] → ranks 1, 2, 3.
        # B ranks them [40, 30, 50, 20] → ranks 1, 2, 3, 4.
        # Both rank 30 (rank 3 in A, rank 2 in B) → strongest fused.
        ret_a = _FakeRetriever("a", {("d1", "thread"): [10, 20, 30]})
        ret_b = _FakeRetriever("b", {("d1", "thread"): [40, 30, 50, 20]})
        result = run_retrievers([ret_a, ret_b], context=_make_context())
        fused_order = result[("d1", "thread")]
        # 30 appears in both lists with reasonable ranks → must be at top.
        self.assertEqual(fused_order[0], 30)
        # All five distinct sentence IDs are present.
        self.assertEqual(set(fused_order), {10, 20, 30, 40, 50})
        # Single-doc lists pass through without RRF re-shuffle.
        ret_solo = _FakeRetriever("solo", {("d1", "thread"): [10, 20]})
        result_solo = run_retrievers([ret_solo], context=_make_context())
        self.assertEqual(result_solo[("d1", "thread")], [10, 20])

    def test_retrievers_with_disjoint_dests_merge(self) -> None:
        ret_a = _FakeRetriever("a", {("d1", "thread"): [10]})
        ret_b = _FakeRetriever("b", {("d2", "thread"): [20]})
        result = run_retrievers([ret_a, ret_b], context=_make_context())
        self.assertEqual(
            result,
            {("d1", "thread"): [10], ("d2", "thread"): [20]},
        )

    def test_failing_retriever_does_not_poison_others(self) -> None:
        ret_a = _FakeRetriever("a", {("d1", "thread"): [10]})
        ret_b = _BoomRetriever()
        ret_c = _FakeRetriever("c", {("d1", "thread"): [20]})
        result = run_retrievers([ret_a, ret_b, ret_c], context=_make_context())
        # A and C still contribute; B's exception is swallowed.
        self.assertEqual(result, {("d1", "thread"): [10, 20]})


class LexicalRetrieverTests(SimpleTestCase):
    """Group C.2 — token-overlap lexical retriever."""

    @staticmethod
    def _record(title: str, scope_title: str = ""):
        """Lightweight stand-in for ContentRecord.

        SimpleTestCase doesn't hit the DB; the retriever only reads
        ``.title`` + ``.scope_title``, so a SimpleNamespace suffices.
        """
        from types import SimpleNamespace

        return SimpleNamespace(title=title, scope_title=scope_title)

    def test_disabled_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import LexicalRetriever

        ret = LexicalRetriever(enabled=False)
        result = ret.retrieve(_make_context())
        self.assertEqual(result, {})

    def test_no_overlap_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import LexicalRetriever

        ret = LexicalRetriever(enabled=True)
        records = {
            (1, "thread"): self._record("alpha beta gamma"),
            (2, "thread"): self._record("delta epsilon zeta"),
        }
        sentence_ids = {(1, "thread"): [10], (2, "thread"): [20]}
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
            )
        )
        # Dest's only host candidate is itself (filtered out) →
        # empty.
        self.assertEqual(result, {})

    def test_overlap_emits_top_k_hosts(self) -> None:
        from apps.pipeline.services.candidate_retrievers import LexicalRetriever

        ret = LexicalRetriever(enabled=True)
        records = {
            (1, "thread"): self._record("python tutorial guide"),
            (2, "thread"): self._record("python beginner intro"),
            (3, "thread"): self._record("ruby on rails"),
            (4, "thread"): self._record("python advanced patterns"),
        }
        sentence_ids = {
            (1, "thread"): [10],
            (2, "thread"): [20, 21],
            (3, "thread"): [30],
            (4, "thread"): [40, 41],
        }
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
                top_k=3,
            )
        )
        # Hosts 2 + 4 share "python" with dest 1 → both contribute.
        # Host 3 shares nothing → excluded.
        # Host 1 == dest → excluded.
        sids = result[(1, "thread")]
        self.assertCountEqual(sids, [20, 21, 40, 41])

    def test_stopwords_dropped(self) -> None:
        """Stopwords should never produce overlap on their own."""
        from apps.pipeline.services.candidate_retrievers import LexicalRetriever

        ret = LexicalRetriever(enabled=True)
        records = {
            (1, "thread"): self._record("the and that"),
            (2, "thread"): self._record("the or this"),
        }
        sentence_ids = {
            (1, "thread"): [10],
            (2, "thread"): [20],
        }
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
            )
        )
        # All non-stopword content tokens are < 3 chars or filtered;
        # no real overlap → empty.
        self.assertEqual(result, {})

    def test_short_tokens_filtered(self) -> None:
        from apps.pipeline.services.candidate_retrievers import LexicalRetriever

        ret = LexicalRetriever(enabled=True, min_token_length=4)
        records = {
            (1, "thread"): self._record("foo bar baz"),
            (2, "thread"): self._record("foo bar baz"),
        }
        sentence_ids = {
            (1, "thread"): [10],
            (2, "thread"): [20],
        }
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
            )
        )
        # All tokens are 3 chars; min_token_length=4 → empty.
        self.assertEqual(result, {})


class QueryExpansionRetrieverTests(SimpleTestCase):
    """Group C.3 — pseudo-relevance feedback retriever (pick #27)."""

    @staticmethod
    def _record(title: str, scope_title: str = ""):
        from types import SimpleNamespace

        return SimpleNamespace(title=title, scope_title=scope_title)

    def test_disabled_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import (
            QueryExpansionRetriever,
        )

        ret = QueryExpansionRetriever(enabled=False)
        self.assertEqual(ret.retrieve(_make_context()), {})

    def test_no_overlap_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import (
            QueryExpansionRetriever,
        )

        ret = QueryExpansionRetriever(enabled=True)
        records = {
            (1, "thread"): self._record("alpha"),
            (2, "thread"): self._record("beta"),
        }
        sentence_ids = {(1, "thread"): [10], (2, "thread"): [20]}
        self.assertEqual(
            ret.retrieve(
                _make_context(
                    destination_keys=((1, "thread"),),
                    content_records=records,
                    content_to_sentence_ids=sentence_ids,
                )
            ),
            {},
        )

    def test_expansion_pulls_in_synonyms(self) -> None:
        """Expanded query surfaces hosts that share PRF-discovered terms."""
        from apps.pipeline.services.candidate_retrievers import (
            QueryExpansionRetriever,
        )

        # Dest title is "python tutorial". Hosts 2-4 are "python
        # variant" pages — they share "python" with the dest, so
        # they're pseudo-relevant. Their *other* tokens (tutorial,
        # guide, beginner) become expansion terms when they appear
        # in ≥ 2 PRF docs. Host 5 has only "tutorial" (no python)
        # — without expansion it'd be invisible; with expansion,
        # it surfaces because "tutorial" became an expansion term.
        records = {
            (1, "thread"): self._record("python tutorial"),  # dest
            (2, "thread"): self._record("python tutorial guide"),
            (3, "thread"): self._record("python beginner tutorial"),
            (4, "thread"): self._record("python advanced tutorial"),
            (5, "thread"): self._record("ruby tutorial guide"),
            (6, "thread"): self._record("unrelated topic"),
        }
        sentence_ids = {k: [k[0] * 10] for k in records}

        # Pick min_document_frequency=2 so common terms across the
        # PRF set surface. PRF top_n=4 covers hosts 2-4.
        ret = QueryExpansionRetriever(
            enabled=True,
            prf_top_n=4,
            expansion_terms=5,
            min_document_frequency=2,
        )
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
                top_k=10,
            )
        )
        sids = result.get((1, "thread"), [])
        # Host 5 should now appear (carried in by "tutorial" expansion).
        # Host 6 should NOT appear (no overlap with original or expanded).
        self.assertIn(50, sids)
        self.assertNotIn(60, sids)

    def test_falls_back_to_lexical_when_too_few_prf_docs(self) -> None:
        """Single PRF doc → no expansion; behaves like LexicalRetriever."""
        from apps.pipeline.services.candidate_retrievers import (
            QueryExpansionRetriever,
        )

        records = {
            (1, "thread"): self._record("python tutorial"),  # dest
            (2, "thread"): self._record("python beginner"),
        }
        sentence_ids = {(1, "thread"): [10], (2, "thread"): [20]}
        ret = QueryExpansionRetriever(enabled=True, prf_top_n=10, expansion_terms=5)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids=sentence_ids,
            )
        )
        # Only host 2 shares "python" with dest; PRF set is size 1
        # so no expansion runs. Output is the same as plain lexical.
        self.assertEqual(result.get((1, "thread")), [20])


class SemanticRetrieverTests(SimpleTestCase):
    """SemanticRetriever delegates to the original semantic function."""

    def test_delegates_to_stage1_semantic_candidates(self) -> None:
        sentinel = {("d1", "thread"): [99]}
        ret = SemanticRetriever()
        with patch(
            "apps.pipeline.services.pipeline_stages._stage1_semantic_candidates",
            return_value=sentinel,
        ) as mock_func:
            result = ret.retrieve(
                _make_context(
                    destination_keys=(("d1", "thread"),),
                    dest_embeddings=np.zeros((1, 4), dtype=np.float32),
                    top_k=3,
                )
            )
        self.assertIs(result, sentinel)
        mock_func.assert_called_once()
        # Arg-passing sanity: kwargs include the top_k and block_size.
        kwargs = mock_func.call_args.kwargs
        self.assertEqual(kwargs["top_k"], 3)
        self.assertEqual(kwargs["block_size"], 256)


class Stage1CandidatesIntegrationTests(SimpleTestCase):
    """The legacy `_stage1_candidates` entry point still works."""

    def test_uses_default_registry(self) -> None:
        from apps.pipeline.services.pipeline_stages import _stage1_candidates

        sentinel = {("d1", "thread"): [42, 43]}
        with patch(
            "apps.pipeline.services.pipeline_stages._stage1_semantic_candidates",
            return_value=sentinel,
        ):
            result = _stage1_candidates(
                destination_keys=(("d1", "thread"),),
                dest_embeddings=np.zeros((1, 4), dtype=np.float32),
                content_records={},
                content_to_sentence_ids={},
                top_k=3,
                block_size=256,
            )
        self.assertEqual(result, sentinel)

    def test_accepts_custom_retrievers_list(self) -> None:
        from apps.pipeline.services.pipeline_stages import _stage1_candidates

        ret = _FakeRetriever("custom", {("d1", "thread"): [7, 8, 9]})
        result = _stage1_candidates(
            destination_keys=(("d1", "thread"),),
            dest_embeddings=np.zeros((1, 4), dtype=np.float32),
            content_records={},
            content_to_sentence_ids={},
            top_k=3,
            block_size=256,
            retrievers=[ret],
        )
        self.assertEqual(result, {("d1", "thread"): [7, 8, 9]})


class XenForoBM25RetrieverTests(SimpleTestCase):
    """XenForo Enhanced Search backed BM25 retriever (Path A).

    Pure ``SimpleTestCase`` — the search client is mocked end-to-end so
    no settings (``XENFORO_BASE_URL`` / ``XENFORO_API_KEY``) are needed
    and no HTTP is performed.
    """

    @staticmethod
    def _record(title: str, scope_title: str = ""):
        from types import SimpleNamespace

        return SimpleNamespace(title=title, scope_title=scope_title)

    @staticmethod
    def _hit(
        content_id: int,
        content_type: str = "thread",
        title: str = "",
        score: float = 1.0,
    ):
        from apps.sync.services.xenforo_search import XFSearchHit

        return XFSearchHit(
            content_id=content_id,
            content_type=content_type,
            title=title,
            snippet="",
            score=score,
            raw={},
        )

    def test_disabled_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        ret = XenForoBM25Retriever(enabled=False)
        result = ret.retrieve(_make_context())
        self.assertEqual(result, {})

    def test_short_query_skipped(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        fake_client = _FakeXFSearchClient([])
        ret = XenForoBM25Retriever(enabled=True, client=fake_client, min_query_length=5)
        records = {(1, "thread"): self._record("hi")}  # below min_query_length
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records=records,
                content_to_sentence_ids={(1, "thread"): [10]},
            )
        )
        self.assertEqual(result, {})

    def test_self_link_filtered(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        # XF returns the destination itself in its own search results
        # (a real failure mode) → retriever must filter it out.
        fake_client = _FakeXFSearchClient(
            [self._hit(content_id=1, content_type="thread")]
        )
        ret = XenForoBM25Retriever(enabled=True, client=fake_client)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records={(1, "thread"): self._record("python tutorial")},
                content_to_sentence_ids={(1, "thread"): [10]},
            )
        )
        self.assertEqual(result, {})

    def test_unknown_host_filtered(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        # XF returns a thread we haven't imported → no entry in
        # content_to_sentence_ids → retriever silently drops it.
        fake_client = _FakeXFSearchClient(
            [self._hit(content_id=999, content_type="thread")]
        )
        ret = XenForoBM25Retriever(enabled=True, client=fake_client)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records={(1, "thread"): self._record("python tutorial")},
                content_to_sentence_ids={(1, "thread"): [10]},
            )
        )
        self.assertEqual(result, {})

    def test_returns_sentence_ids_for_each_known_hit(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        fake_client = _FakeXFSearchClient(
            [
                self._hit(content_id=2, content_type="thread"),
                self._hit(content_id=3, content_type="thread"),
            ]
        )
        ret = XenForoBM25Retriever(enabled=True, client=fake_client)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records={
                    (1, "thread"): self._record("python tutorial guide"),
                    (2, "thread"): self._record("python beginner intro"),
                    (3, "thread"): self._record("python advanced patterns"),
                },
                content_to_sentence_ids={
                    (1, "thread"): [10],
                    (2, "thread"): [20, 21],
                    (3, "thread"): [30, 31, 32],
                },
            )
        )
        self.assertEqual(result, {(1, "thread"): [20, 21, 30, 31, 32]})

    def test_dedups_same_host_appearing_twice(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        # XF can return the same thread twice if it had duplicate posts
        # ranked separately. We must dedup so the unifier doesn't see
        # the same sentence_ids twice.
        fake_client = _FakeXFSearchClient(
            [
                self._hit(content_id=2, content_type="thread"),
                self._hit(content_id=2, content_type="thread"),
            ]
        )
        ret = XenForoBM25Retriever(enabled=True, client=fake_client)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records={
                    (1, "thread"): self._record("python tutorial"),
                    (2, "thread"): self._record("python beginner"),
                },
                content_to_sentence_ids={
                    (1, "thread"): [10],
                    (2, "thread"): [20, 21],
                },
            )
        )
        self.assertEqual(result, {(1, "thread"): [20, 21]})

    def test_search_client_unavailable_logs_and_returns_empty(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        ret = XenForoBM25Retriever(enabled=True)  # client=None → lazy-resolve
        with patch(
            "apps.sync.services.xenforo_search.XenForoSearchClient",
            side_effect=ValueError("XENFORO_BASE_URL missing"),
        ):
            result = ret.retrieve(
                _make_context(
                    destination_keys=((1, "thread"),),
                    content_records={(1, "thread"): self._record("python tutorial")},
                    content_to_sentence_ids={(1, "thread"): [10]},
                )
            )
        self.assertEqual(result, {})

    def test_build_query_combines_title_and_distinct_scope(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        record = self._record(title="Bug X workaround", scope_title="Support Forum")
        self.assertEqual(
            XenForoBM25Retriever._build_query(record),
            "Bug X workaround Support Forum",
        )

    def test_build_query_uses_title_only_when_scope_already_in_title(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        # Scope is a substring of the title (case-insensitive) → no
        # value in repeating it.
        record = self._record(
            title="Bug X workaround in Support Forum",
            scope_title="Support Forum",
        )
        self.assertEqual(
            XenForoBM25Retriever._build_query(record),
            "Bug X workaround in Support Forum",
        )

    def test_build_query_handles_blank_title(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        record = self._record(title="", scope_title="Support Forum")
        self.assertEqual(
            XenForoBM25Retriever._build_query(record), "Support Forum"
        )

    def test_search_failure_returns_empty_for_that_dest(self) -> None:
        from apps.pipeline.services.candidate_retrievers import XenForoBM25Retriever

        # XF search returns [] on failure (handled inside the search
        # client). Retriever must treat empty list as "no candidates"
        # for this dest, not crash.
        fake_client = _FakeXFSearchClient([])
        ret = XenForoBM25Retriever(enabled=True, client=fake_client)
        result = ret.retrieve(
            _make_context(
                destination_keys=((1, "thread"),),
                content_records={(1, "thread"): self._record("python tutorial")},
                content_to_sentence_ids={(1, "thread"): [10]},
            )
        )
        self.assertEqual(result, {})


class _FakeXFSearchClient:
    """Minimal stub matching ``XenForoSearchClient.search_threads``."""

    def __init__(self, hits):
        self._hits = list(hits)

    def search_threads(self, query, *, limit=200):
        return list(self._hits)
