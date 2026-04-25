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
        """Retriever B's overlapping IDs are dropped; new ones append in order."""
        ret_a = _FakeRetriever(
            "a", {("d1", "thread"): [10, 20, 30]}
        )
        ret_b = _FakeRetriever(
            "b", {("d1", "thread"): [20, 40, 30, 50]}
        )
        result = run_retrievers([ret_a, ret_b], context=_make_context())
        # Order: A's [10, 20, 30] first; then B contributes 40, 50
        # (already-seen 20 + 30 are dropped).
        self.assertEqual(result, {("d1", "thread"): [10, 20, 30, 40, 50]})

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
