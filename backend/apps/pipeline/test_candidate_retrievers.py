"""Tests for Group C.1 — Stage-1 list-of-retrievers refactor.

Verifies the abstraction in :mod:`apps.pipeline.services.candidate_retrievers`:

- ``SemanticRetriever`` produces the same output as the legacy single-
  function path (it wraps the same body).
- ``run_retrievers`` correctly unifies multiple retrievers' output
  with dedup-while-preserving-order.
- A failing retriever doesn't poison the others' contributions.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.candidate_retrievers import (
    CandidateRetriever,
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
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].name, "semantic")
        self.assertIsInstance(regs[0], SemanticRetriever)


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
        ret_a = _FakeRetriever(
            "a", {("d1", "thread"): [10, 20, 30]}
        )
        ret_b = _FakeRetriever(
            "b", {("d1", "thread"): [20, 40, 30, 50]}
        )
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
        result = run_retrievers(
            [ret_a, ret_b, ret_c], context=_make_context()
        )
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
