"""NDCG smoke test for Group C Stage-1 candidate fusion.

Quality-gate evidence that the Group C retriever stack (semantic +
lexical + RRF + query-expansion) doesn't regress NDCG vs the
legacy semantic-only path. Uses a synthetic corpus where the ground-
truth top hosts per destination are known by construction, so we can
score each retriever configuration.

This is *not* a benchmark for production NDCG (no ground-truth label
data here yet) — it's a smoke test that says "the fusion machinery
behaves no worse than its weakest input on a controlled corpus" and
"adding a complementary retriever helps when its signal is real".
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.candidate_retrievers import (
    LexicalRetriever,
    QueryExpansionRetriever,
    RetrievalContext,
    run_retrievers,
)


def _ndcg_at_k(predicted_order, ideal_relevances, *, k: int = 10) -> float:
    """Plain NDCG@K — gain = relevance, discount = log2(rank+2)."""
    if not predicted_order:
        return 0.0
    actual = predicted_order[:k]
    dcg = sum(
        ideal_relevances.get(item, 0.0) / math.log2(rank + 2.0)
        for rank, item in enumerate(actual)
    )
    ideal_sorted = sorted(ideal_relevances.values(), reverse=True)[:k]
    idcg = sum(rel / math.log2(rank + 2.0) for rank, rel in enumerate(ideal_sorted))
    if idcg <= 0:
        return 0.0
    return dcg / idcg


class _FakeSemanticRetriever:
    """Stand-in for the production SemanticRetriever.

    The real retriever needs an embedding store + FAISS — too heavy
    for a smoke test. This fake takes a hard-coded per-dest list of
    sentence IDs (the "semantic" ranking). It mirrors the protocol's
    contract exactly: ``name`` + ``retrieve(context) → dict``.
    """

    name = "semantic"

    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def retrieve(self, context: RetrievalContext) -> dict:
        return {
            dest: list(sids)
            for dest, sids in self._mapping.items()
            if dest in context.destination_keys
        }


def _record(title: str, scope_title: str = ""):
    """Lightweight stand-in for ContentRecord (only title/scope_title read)."""
    return SimpleNamespace(title=title, scope_title=scope_title)


def _make_corpus():
    """Synthetic corpus where the truth-set per destination is known.

    Three destinations:
    - dest 1: "python tutorial" — ideal hosts share python-tutorial vocab.
    - dest 2: "machine learning intro" — ideal hosts share ML vocab.
    - dest 3: "ruby rails guide" — ideal hosts share ruby-rails vocab.

    Hosts 100-115 cover those topics; hosts 200-204 are noise.

    Ideal relevances per dest (3 = perfect, 2 = strong, 1 = weak,
    0 = unrelated). These come from constructing the corpus, not from
    any retriever's output.
    """
    records = {
        # destinations
        (1, "thread"): _record("python tutorial"),
        (2, "thread"): _record("machine learning intro"),
        (3, "thread"): _record("ruby rails guide"),
        # python-related hosts
        (100, "thread"): _record("python tutorial guide"),
        (101, "thread"): _record("python beginner walkthrough"),
        (102, "thread"): _record("advanced python patterns"),
        (103, "thread"): _record("scripting with python"),
        # ML-related hosts
        (110, "thread"): _record("introduction to machine learning"),
        (111, "thread"): _record("deep learning intro"),
        (112, "thread"): _record("ml model intro"),
        # ruby-related hosts
        (113, "thread"): _record("ruby on rails guide"),
        (114, "thread"): _record("rails framework"),
        (115, "thread"): _record("ruby beginner intro"),
        # noise
        (200, "thread"): _record("cooking recipes"),
        (201, "thread"): _record("travel destinations"),
        (202, "thread"): _record("financial advice"),
        (203, "thread"): _record("gardening tips"),
        (204, "thread"): _record("woodworking projects"),
    }

    sentence_ids = {key: [key[0] * 10] for key in records}

    # Ground-truth relevance: every host's first sentence ID gets a
    # relevance based on how well its title matches the destination.
    truth = {
        (1, "thread"): {  # python tutorial
            1000: 3, 1010: 3,  # 100, 101 (best)
            1020: 2, 1030: 2,  # 102, 103 (okay)
        },
        (2, "thread"): {  # ML intro
            1100: 3, 1110: 3, 1120: 3,
        },
        (3, "thread"): {  # ruby rails guide
            1130: 3, 1140: 3, 1150: 2,
        },
    }
    return records, sentence_ids, truth


def _measure(retrievers, context, truth) -> dict:
    """Run *retrievers* through ``run_retrievers`` and return per-dest NDCG@10."""
    fused = run_retrievers(retrievers, context=context)
    return {
        dest: _ndcg_at_k(fused.get(dest, []), truth[dest])
        for dest in truth
    }


class Stage1FusionNdcgTests(SimpleTestCase):
    """Asserts Group C retriever fusion never regresses NDCG vs the
    semantic-only baseline on a controlled corpus."""

    def setUp(self) -> None:
        self.records, self.sentence_ids, self.truth = _make_corpus()
        # Fake semantic retriever — gives the "right" hosts for python
        # and ML, but a poor order for ruby (top-1 is noise). This
        # simulates the dense-embedding case where similar topics
        # cluster but novel vocabulary scores low.
        self.semantic_mapping = {
            (1, "thread"): [1000, 1010, 1020, 1030, 2000, 2010],
            (2, "thread"): [1100, 1110, 1120, 2020, 2030, 2040],
            (3, "thread"): [2000, 2010, 1130, 1140, 1150, 2030],  # noise on top!
        }
        # Build the retrieval context once.
        keys = tuple(self.truth.keys())
        self.context = RetrievalContext(
            destination_keys=keys,
            dest_embeddings=np.zeros((len(keys), 4), dtype=np.float32),
            content_records=self.records,
            content_to_sentence_ids=self.sentence_ids,
            top_k=10,
            block_size=64,
        )

    def test_lexical_alone_recovers_ruby_case(self) -> None:
        """Plain LexicalRetriever finds the truly-similar ruby hosts."""
        lex = LexicalRetriever(enabled=True)
        ndcg_per_dest = _measure([lex], self.context, self.truth)
        # Lexical for dest 3 should easily beat the noisy semantic
        # ordering on the ruby case.
        self.assertGreater(ndcg_per_dest[(3, "thread")], 0.7)

    def test_fusion_beats_or_ties_semantic_only(self) -> None:
        """RRF(semantic, lexical) ≥ semantic-only on every destination."""
        semantic = _FakeSemanticRetriever(self.semantic_mapping)
        baseline = _measure([semantic], self.context, self.truth)
        fused = _measure(
            [semantic, LexicalRetriever(enabled=True)],
            self.context,
            self.truth,
        )

        for dest in self.truth:
            self.assertGreaterEqual(
                fused[dest],
                # RRF can rearrange so allow a tiny epsilon for the
                # already-perfect cases (where semantic's top-K
                # already covers all relevant items).
                baseline[dest] - 1e-9,
                f"NDCG regressed on {dest}: "
                f"baseline={baseline[dest]:.4f} fused={fused[dest]:.4f}",
            )

    def test_fusion_strictly_beats_semantic_when_semantic_was_noisy(self) -> None:
        """On the ruby case where semantic ranked noise on top, fusion
        should land the right answer above noise."""
        semantic = _FakeSemanticRetriever(self.semantic_mapping)
        baseline = _measure([semantic], self.context, self.truth)
        fused = _measure(
            [semantic, LexicalRetriever(enabled=True)],
            self.context,
            self.truth,
        )
        # The ruby case had semantic ranking [noise, noise, ruby...] →
        # adding a lexical retriever that finds ruby hosts via title
        # tokens must improve NDCG strictly.
        ruby = (3, "thread")
        self.assertGreater(
            fused[ruby],
            baseline[ruby] + 1e-3,
            "Fusion did not improve the ruby case where lexical signal exists",
        )

    def test_query_expansion_adds_value_on_synonym_case(self) -> None:
        """QueryExpansionRetriever should pull in semantically-related
        hosts that share PRF expansion terms with the destination."""
        # For this assertion, build a corpus where some hosts share
        # ONLY expansion terms with the destination (not the original
        # title). Use the synonym-pull-in flow from the unit test
        # but assert NDCG.
        records = {
            (1, "thread"): _record("python tutorial"),
            (10, "thread"): _record("python tutorial guide"),
            (11, "thread"): _record("python tutorial beginner"),
            (12, "thread"): _record("python beginner intro"),
            (13, "thread"): _record("ruby tutorial"),
            (14, "thread"): _record("unrelated topic"),
        }
        sentence_ids = {k: [k[0] * 10] for k in records}
        # Truth: hosts that mention "python" OR "tutorial" are
        # genuinely relevant (high gain); the ruby tutorial host
        # is partially relevant (one shared term); the unrelated
        # one is noise.
        truth = {
            (1, "thread"): {
                100: 3, 110: 3, 120: 2, 130: 2,
            },
        }
        keys = tuple(truth.keys())
        ctx = RetrievalContext(
            destination_keys=keys,
            dest_embeddings=np.zeros((len(keys), 4), dtype=np.float32),
            content_records=records,
            content_to_sentence_ids=sentence_ids,
            top_k=10,
            block_size=64,
        )
        lex = LexicalRetriever(enabled=True)
        qe = QueryExpansionRetriever(
            enabled=True,
            prf_top_n=4,
            expansion_terms=5,
            min_document_frequency=2,
        )
        ndcg_lex = _measure([lex], ctx, truth)
        ndcg_qe = _measure([qe], ctx, truth)
        # QE shouldn't be worse than lex (within numerical noise) on
        # this constructed case where expansion terms are a strict
        # superset of the original query terms.
        self.assertGreaterEqual(
            ndcg_qe[(1, "thread")],
            ndcg_lex[(1, "thread")] - 1e-9,
            "QueryExpansionRetriever regressed below LexicalRetriever",
        )

    def test_three_retriever_fusion_caps_at_or_above_two(self) -> None:
        """[semantic, lexical, query-expansion] ≥ [semantic, lexical] per dest."""
        semantic = _FakeSemanticRetriever(self.semantic_mapping)
        lex = LexicalRetriever(enabled=True)
        qe = QueryExpansionRetriever(
            enabled=True, prf_top_n=4, expansion_terms=5, min_document_frequency=1
        )
        two = _measure([semantic, lex], self.context, self.truth)
        three = _measure([semantic, lex, qe], self.context, self.truth)
        for dest in self.truth:
            # Three-retriever fusion can't be much worse than two —
            # allow a small tolerance for RRF reorderings on already-
            # perfect cases.
            self.assertGreaterEqual(
                three[dest],
                two[dest] - 0.05,
                f"3-way fusion regressed too far on {dest}: "
                f"two={two[dest]:.4f} three={three[dest]:.4f}",
            )
