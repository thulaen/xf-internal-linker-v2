"""Tests for the Phase 6 ranker-time contribution dispatcher.

Covers the public surface in
``apps.pipeline.services.phase6_ranker_contribution``:

- Six wired adapters (VADER, KenLM, LDA, Node2Vec, BPR, FM) — each
  exercised through both its cold-start path (no trained model →
  0.0) and a happy path where a paper-backed input produces a
  non-zero score.
- ``Phase6RankerContribution.contribute_total`` aggregates weighted
  per-pick contributions.
- ``Phase6RankerContribution.per_pick_breakdown`` returns the raw
  pre-weight scores for diagnostics.
- ``build_phase6_contribution`` returns ``None`` when no pick has a
  non-zero weight (cold-start / disabled paths) and reads weights
  from AppSetting once non-zero values are seeded.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.pipeline.services import phase6_ranker_contribution as p6
from apps.pipeline.services.phase6_ranker_contribution import AdapterContext


def _ctx(
    *,
    host: str = "",
    dest: str = "",
    host_key: tuple[int, str] | None = None,
    destination_key: tuple[int, str] | None = None,
    score_components: dict[str, float] | None = None,
    anchor_confidence: str | None = None,
) -> AdapterContext:
    return AdapterContext(
        host_sentence_text=host,
        destination_text=dest,
        host_key=host_key,
        destination_key=destination_key,
        score_components=score_components,
        anchor_confidence=anchor_confidence,
    )


class DispatcherSimpleTests(SimpleTestCase):
    def test_no_weights_returns_zero(self) -> None:
        c = p6.Phase6RankerContribution(weights={})
        self.assertEqual(c.contribute_total(_ctx(host="x")), 0.0)

    def test_zero_weight_skipped(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.0})
        self.assertEqual(c.contribute_total(_ctx(host="happy day")), 0.0)

    def test_unknown_pick_skipped(self) -> None:
        c = p6.Phase6RankerContribution(weights={"non_existent_pick": 1.0})
        self.assertEqual(c.contribute_total(_ctx(host="x")), 0.0)

    def test_is_active_false_when_all_zero(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.0})
        self.assertFalse(c.is_active)

    def test_is_active_true_with_one_nonzero(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.5})
        self.assertTrue(c.is_active)


class VaderAdapterTests(TestCase):
    def setUp(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "true", "description": ""},
        )
        invalidate("vader_sentiment.enabled")

    def test_empty_text_returns_zero(self) -> None:
        self.assertEqual(p6._vader_adapter(_ctx()), 0.0)

    def test_positive_text_returns_positive(self) -> None:
        from apps.sources import vader_sentiment as vs

        if not vs.HAS_VADER:
            self.skipTest("vaderSentiment not installed; adapter returns 0.0")
        self.assertGreater(
            p6._vader_adapter(_ctx(host="This is amazing and wonderful!")),
            0.0,
        )

    def test_negative_text_returns_negative(self) -> None:
        from apps.sources import vader_sentiment as vs

        if not vs.HAS_VADER:
            self.skipTest("vaderSentiment not installed; adapter returns 0.0")
        self.assertLess(
            p6._vader_adapter(_ctx(host="Terrible, awful, the worst day ever.")),
            0.0,
        )


class KenLMAdapterColdStartTests(SimpleTestCase):
    """KenLM has a runtime model dep; without a trained ARPA file we
    expect cold-start = 0.0 contribution. Happy-path lives in the
    integration tests once the W1 trainer fires."""

    def test_empty_text_returns_zero(self) -> None:
        self.assertEqual(p6._kenlm_adapter(_ctx()), 0.0)

    def test_no_model_returns_zero(self) -> None:
        # Simulate the helper returning the neutral score (its
        # documented cold-start path).
        from apps.pipeline.services.kenlm_fluency import FluencyScore

        with patch(
            "apps.pipeline.services.kenlm_fluency.score_fluency",
            return_value=FluencyScore(log_prob=0.0, per_token=0.0, token_count=0),
        ):
            self.assertEqual(p6._kenlm_adapter(_ctx(host="any text")), 0.0)

    def test_fluent_per_token_returns_positive(self) -> None:
        from apps.pipeline.services.kenlm_fluency import FluencyScore

        # per_token = -2 (fluent English) → tanh(+1) ≈ 0.76
        with patch(
            "apps.pipeline.services.kenlm_fluency.score_fluency",
            return_value=FluencyScore(log_prob=-10.0, per_token=-2.0, token_count=5),
        ):
            self.assertGreater(p6._kenlm_adapter(_ctx(host="x")), 0.5)

    def test_rare_per_token_returns_negative(self) -> None:
        from apps.pipeline.services.kenlm_fluency import FluencyScore

        # per_token = -5 → tanh(-2) ≈ -0.96
        with patch(
            "apps.pipeline.services.kenlm_fluency.score_fluency",
            return_value=FluencyScore(log_prob=-25.0, per_token=-5.0, token_count=5),
        ):
            self.assertLess(p6._kenlm_adapter(_ctx(host="x")), -0.5)


class LDAAdapterColdStartTests(SimpleTestCase):
    def test_empty_inputs_return_zero(self) -> None:
        self.assertEqual(p6._lda_adapter(_ctx()), 0.0)
        self.assertEqual(p6._lda_adapter(_ctx(host="x")), 0.0)

    def test_no_model_returns_zero(self) -> None:
        from apps.pipeline.services.lda_topics import EMPTY_DISTRIBUTION

        with patch(
            "apps.pipeline.services.lda_topics.infer_topics",
            return_value=EMPTY_DISTRIBUTION,
        ):
            self.assertEqual(
                p6._lda_adapter(_ctx(host="topic a", dest="topic b")),
                0.0,
            )

    def test_high_overlap_returns_positive(self) -> None:
        from apps.pipeline.services.lda_topics import TopicDistribution

        same = TopicDistribution(weights=[(0, 0.9), (1, 0.1)])
        with patch(
            "apps.pipeline.services.lda_topics.infer_topics",
            return_value=same,
        ):
            # Cosine of identical → 1.0; minus 0.5 → +0.5
            self.assertGreater(p6._lda_adapter(_ctx(host="x", dest="y")), 0.4)

    def test_no_shared_topics_returns_zero_not_negative(self) -> None:
        """Audit bug A7 — disjoint topic distributions ARE NOT
        anti-evidence. Cosine of orthogonal vectors is 0.0; the
        adapter must return 0.0, NOT -0.5.
        """
        from apps.pipeline.services.lda_topics import TopicDistribution

        host_dist = TopicDistribution(weights=[(0, 0.9), (1, 0.1)])
        dest_dist = TopicDistribution(weights=[(99, 0.9), (100, 0.1)])

        # Sequential calls: first invocation returns host_dist,
        # second returns dest_dist. infer_topics is called twice
        # inside the adapter (once per text).
        call_seq = iter([host_dist, dest_dist])
        with patch(
            "apps.pipeline.services.lda_topics.infer_topics",
            side_effect=lambda *_a, **_k: next(call_seq),
        ):
            self.assertEqual(p6._lda_adapter(_ctx(host="x", dest="y")), 0.0)


class Node2VecAdapterColdStartTests(SimpleTestCase):
    def test_no_keys_returns_zero(self) -> None:
        self.assertEqual(p6._node2vec_adapter(_ctx()), 0.0)

    def test_no_embeddings_returns_zero(self) -> None:
        with patch(
            "apps.pipeline.services.node2vec_embeddings.vector_for",
            return_value=None,
        ):
            self.assertEqual(
                p6._node2vec_adapter(
                    _ctx(host_key=(1, "thread"), destination_key=(2, "thread"))
                ),
                0.0,
            )

    def test_aligned_vectors_return_positive(self) -> None:
        with patch(
            "apps.pipeline.services.node2vec_embeddings.vector_for",
            side_effect=lambda key: [1.0, 0.0, 0.0],
        ):
            self.assertAlmostEqual(
                p6._node2vec_adapter(
                    _ctx(host_key=(1, "thread"), destination_key=(2, "thread"))
                ),
                1.0,
                places=3,
            )

    def test_orthogonal_vectors_return_zero(self) -> None:
        def fake_vector_for(key: str) -> list[float]:
            return [1.0, 0.0] if "1" in key else [0.0, 1.0]

        with patch(
            "apps.pipeline.services.node2vec_embeddings.vector_for",
            side_effect=fake_vector_for,
        ):
            self.assertAlmostEqual(
                p6._node2vec_adapter(
                    _ctx(host_key=(1, "thread"), destination_key=(2, "thread"))
                ),
                0.0,
                places=3,
            )


class BPRAdapterColdStartTests(SimpleTestCase):
    def test_no_keys_returns_zero(self) -> None:
        self.assertEqual(p6._bpr_adapter(_ctx()), 0.0)

    def test_no_model_returns_zero(self) -> None:
        with patch(
            "apps.pipeline.services.bpr_ranking.score_for_user",
            return_value=None,
        ):
            self.assertEqual(
                p6._bpr_adapter(
                    _ctx(host_key=(1, "thread"), destination_key=(2, "thread"))
                ),
                0.0,
            )

    def test_positive_score_returns_positive_bounded(self) -> None:
        # Audit bug A1 fix: trainer uses bare-pk strings ("2"), NOT
        # the (pk, content_type) tuple string. The adapter must
        # match — assert by passing a mock that ONLY honours the
        # bare-pk format.
        with patch(
            "apps.pipeline.services.bpr_ranking.score_for_user",
            return_value={"2": 4.0},
        ):
            r = p6._bpr_adapter(
                _ctx(host_key=(1, "thread"), destination_key=(2, "thread"))
            )
            self.assertGreater(r, 0.0)
            self.assertLess(r, 1.0)  # tanh saturates below 1

    def test_adapter_passes_bare_pks_not_tuple_strings(self) -> None:
        """Audit bug A1 — adapter must use ``str(host_key[0])`` so
        the W1 trainer's user_index lookup hits."""
        captured: dict[str, object] = {}

        def fake_score_for_user(user_id, item_ids):
            captured["user_id"] = user_id
            captured["item_ids"] = list(item_ids)
            return None

        with patch(
            "apps.pipeline.services.bpr_ranking.score_for_user",
            side_effect=fake_score_for_user,
        ):
            p6._bpr_adapter(
                _ctx(host_key=(123, "thread"), destination_key=(456, "thread"))
            )

        self.assertEqual(captured["user_id"], "123")
        self.assertEqual(captured["item_ids"], ["456"])


class FMAdapterColdStartTests(SimpleTestCase):
    def test_no_score_components_returns_zero(self) -> None:
        # Audit bug A2 fix: when score_components is None / empty,
        # the adapter short-circuits to 0.0 (no useful FM input).
        self.assertEqual(p6._fm_adapter(_ctx()), 0.0)
        self.assertEqual(
            p6._fm_adapter(_ctx(host="x", dest="y")),  # text alone is not enough
            0.0,
        )

    def test_no_model_returns_zero(self) -> None:
        with patch(
            "apps.pipeline.services.factorization_machines.predict",
            return_value=None,
        ):
            self.assertEqual(
                p6._fm_adapter(
                    _ctx(score_components={"score_semantic": 0.5})
                ),
                0.0,
            )

    def test_positive_prediction_returns_positive_bounded(self) -> None:
        with patch(
            "apps.pipeline.services.factorization_machines.predict",
            return_value=[2.5],
        ):
            r = p6._fm_adapter(
                _ctx(
                    score_components={"score_semantic": 0.7, "score_keyword": 0.4},
                    anchor_confidence="strong",
                )
            )
            self.assertGreater(r, 0.0)
            self.assertLess(r, 1.0)

    def test_adapter_encodes_trainer_vocabulary(self) -> None:
        """Audit bug A2 — adapter must build a feature dict whose
        keys match the W1 trainer's vocabulary (nine score columns
        + one-hot anchor_confidence)."""
        captured: dict[str, dict] = {}

        def fake_predict(features_list):
            captured["features"] = features_list[0]
            return [0.0]

        with patch(
            "apps.pipeline.services.factorization_machines.predict",
            side_effect=fake_predict,
        ):
            p6._fm_adapter(
                _ctx(
                    score_components={
                        "score_semantic": 0.6,
                        "score_keyword": 0.3,
                        "score_node_affinity": 0.5,
                        "score_quality": 0.4,
                        "score_link_freshness": 0.7,
                        "score_phrase_relevance": 0.2,
                        "score_field_aware_relevance": 0.1,
                        "score_rare_term_propagation": 0.3,
                        "score_anchor_diversity": 0.5,
                    },
                    anchor_confidence="strong",
                )
            )

        feats = captured["features"]
        # All nine numeric score columns present with the expected
        # values.
        self.assertEqual(feats["score_semantic"], 0.6)
        self.assertEqual(feats["score_keyword"], 0.3)
        self.assertEqual(feats["score_node_affinity"], 0.5)
        self.assertEqual(feats["score_quality"], 0.4)
        self.assertEqual(feats["score_link_freshness"], 0.7)
        self.assertEqual(feats["score_phrase_relevance"], 0.2)
        self.assertEqual(feats["score_field_aware_relevance"], 0.1)
        self.assertEqual(feats["score_rare_term_propagation"], 0.3)
        self.assertEqual(feats["score_anchor_diversity"], 0.5)
        # anchor_confidence one-hot.
        self.assertEqual(feats["anchor_confidence=strong"], 1.0)
        # The old (broken) feature names MUST NOT be present.
        self.assertNotIn("host_text_len", feats)
        self.assertNotIn("destination_text_len", feats)

    def test_missing_anchor_confidence_falls_back_to_none(self) -> None:
        """Mirror the trainer's ``row.get('anchor_confidence') or 'none'``
        default."""
        captured: dict[str, dict] = {}

        with patch(
            "apps.pipeline.services.factorization_machines.predict",
            side_effect=lambda fs: (captured.update(features=fs[0]), [0.0])[1],
        ):
            p6._fm_adapter(
                _ctx(
                    score_components={"score_semantic": 0.5},
                    anchor_confidence=None,
                )
            )
        self.assertEqual(captured["features"]["anchor_confidence=none"], 1.0)


class DispatcherWeightingTests(SimpleTestCase):
    """Verify the weight × adapter math without depending on any real
    helper output."""

    def test_weight_multiplies_adapter_output(self) -> None:
        with patch.dict(p6._ADAPTERS, {"fake_pick": lambda ctx: 0.5}):
            c = p6.Phase6RankerContribution(weights={"fake_pick": 2.0})
            self.assertAlmostEqual(c.contribute_total(_ctx()), 1.0, places=6)

    def test_negative_weight_flips_sign(self) -> None:
        with patch.dict(p6._ADAPTERS, {"fake_pick": lambda ctx: 0.5}):
            c = p6.Phase6RankerContribution(weights={"fake_pick": -1.0})
            self.assertAlmostEqual(c.contribute_total(_ctx()), -0.5, places=6)

    def test_multiple_picks_sum(self) -> None:
        with patch.dict(
            p6._ADAPTERS,
            {
                "pick_a": lambda ctx: 0.3,
                "pick_b": lambda ctx: -0.2,
            },
        ):
            c = p6.Phase6RankerContribution(
                weights={"pick_a": 1.0, "pick_b": 0.5}
            )
            self.assertAlmostEqual(
                c.contribute_total(_ctx()),
                0.3 - 0.1,
                places=6,
            )

    def test_failing_adapter_does_not_crash_total(self) -> None:
        def boom(ctx: AdapterContext) -> float:
            raise RuntimeError("simulated adapter outage")

        with patch.dict(
            p6._ADAPTERS, {"good": lambda ctx: 0.5, "bad": boom}
        ):
            c = p6.Phase6RankerContribution(
                weights={"good": 1.0, "bad": 1.0}
            )
            self.assertAlmostEqual(c.contribute_total(_ctx()), 0.5, places=6)

    def test_per_pick_breakdown_returns_raw_unweighted_scores(self) -> None:
        with patch.dict(
            p6._ADAPTERS,
            {
                "pick_a": lambda ctx: 0.7,
                "pick_b": lambda ctx: -0.3,
            },
        ):
            c = p6.Phase6RankerContribution(
                weights={"pick_a": 100.0, "pick_b": 100.0}
            )
            breakdown = c.per_pick_breakdown(_ctx())
            self.assertAlmostEqual(breakdown["pick_a"], 0.7, places=6)
            self.assertAlmostEqual(breakdown["pick_b"], -0.3, places=6)


class BuildDispatcherTests(TestCase):
    def _invalidate_pick_caches(self) -> None:
        from apps.core.runtime_flags import invalidate

        for pick_name in p6._ADAPTERS:
            invalidate(f"{pick_name}.enabled")

    def _clear_seed_weights(self) -> None:
        """Delete the migration 0046 seeded ``<pick>.ranking_weight``
        rows so the cold-start path can be tested in isolation."""
        from apps.core.models import AppSetting

        AppSetting.objects.filter(
            key__in=[f"{pick}.ranking_weight" for pick in p6._ADAPTERS]
        ).delete()

    def test_global_disabled_returns_none(self) -> None:
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=False)
        self.assertIsNone(result)

    def test_no_weights_set_returns_none(self) -> None:
        # Migration 0046 seeds non-zero weights for every pick. The
        # cold-start path is "all weights are zero/missing", so we
        # delete the seed rows for the duration of this test.
        self._clear_seed_weights()
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNone(result)

    def test_weight_picked_up_from_appsetting(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="vader_sentiment.ranking_weight",
            defaults={"value": "0.05", "description": ""},
        )
        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "true", "description": ""},
        )
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.weights["vader_sentiment"], 0.05, places=6)

    def test_disabled_pick_excluded(self) -> None:
        # Clear migration 0046's seeded weights so we can isolate
        # VADER's behaviour: only VADER has a weight; VADER is
        # disabled; dispatcher returns None.
        self._clear_seed_weights()
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="vader_sentiment.ranking_weight",
            defaults={"value": "0.05", "description": ""},
        )
        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "false", "description": ""},
        )
        # Disable every other pick too — otherwise the migration's
        # seeded enabled flags pull them into the dispatcher.
        for pick in p6._ADAPTERS:
            if pick == "vader_sentiment":
                continue
            AppSetting.objects.update_or_create(
                key=f"{pick}.enabled",
                defaults={"value": "false", "description": ""},
            )
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNone(result)

    def test_full_recommended_preset_yields_six_active_picks(self) -> None:
        """Seed all six paper-backed default weights and verify the
        dispatcher loads them all."""
        from apps.core.models import AppSetting

        defaults = {
            "vader_sentiment": "0.05",
            "kenlm": "0.05",
            "lda": "0.10",
            "node2vec": "0.05",
            "bpr": "0.05",
            "factorization_machines": "0.10",
        }
        for pick_name, weight in defaults.items():
            AppSetting.objects.update_or_create(
                key=f"{pick_name}.ranking_weight",
                defaults={"value": weight, "description": ""},
            )
            AppSetting.objects.update_or_create(
                key=f"{pick_name}.enabled",
                defaults={"value": "true", "description": ""},
            )
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNotNone(result)
        self.assertEqual(set(result.weights.keys()), set(defaults.keys()))
        # Sum of paper-backed defaults: 0.40 (small relative to the
        # existing 15-component composite — sane co-existence).
        self.assertAlmostEqual(sum(result.weights.values()), 0.40, places=6)

    def test_weight_reads_are_batched_into_one_query(self) -> None:
        """Audit bug A4 — `_load_all_weights` issues exactly ONE
        AppSetting query for all six weights, not six separate
        ``filter().first()`` round trips.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Make sure migration 0046 is in place by calling the
        # batched loader once.
        self._invalidate_pick_caches()
        with CaptureQueriesContext(connection) as captured:
            p6._load_all_weights()

        # Count queries that touched core_appsetting. Other DB hits
        # (auth fixtures, etc.) are not under test.
        appsetting_queries = [
            q for q in captured.captured_queries if "core_appsetting" in q["sql"]
        ]
        self.assertEqual(
            len(appsetting_queries),
            1,
            f"Expected 1 batched AppSetting query, got "
            f"{len(appsetting_queries)}: "
            f"{[q['sql'] for q in appsetting_queries]}",
        )
