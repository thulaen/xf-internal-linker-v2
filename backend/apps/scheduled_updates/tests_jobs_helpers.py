"""Tests for the pure-function helpers extracted from scheduled_updates/jobs.py.

These helpers replaced ~700 lines of inlined boilerplate across 11 long
``run_*`` scheduled-job entrypoints. Each is independently testable in
``SimpleTestCase`` (no DB).
"""

from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.scheduled_updates.jobs import (
    _ANCHOR_STATS_MIN_ANCHORS,
    _build_fm_features,
    _build_node2vec_edge_triples,
    _coerce_setting_float,
    _coerce_setting_int,
    _compute_anchor_entropy_stats,
    _ensure_model_output_path,
    _FM_FEEDBACK_LOOKBACK_DAYS,
    _FM_MIN_TRAINING_ROWS,
    _FM_SCORE_COLUMNS,
    _KENLM_MIN_CORPUS_LINES,
    _KENLM_MIN_SENTENCE_CHARS,
    _LDA_MIN_DOCUMENT_COUNT,
    _LDA_MIN_TOKEN_LENGTH,
    _median,
    _read_meta_hpo_applied_at,
    _summarize_cascade_snapshots,
    _summarize_position_bias_snapshots,
)


class CoerceSettingIntTests(SimpleTestCase):
    """Verify int coercion from a bulk-loaded raw map."""

    def test_missing_key_returns_default(self):
        self.assertEqual(_coerce_setting_int({}, "missing", 42), 42)

    def test_valid_int_string(self):
        self.assertEqual(
            _coerce_setting_int({"k": "100"}, "k", 0),
            100,
        )

    def test_invalid_string_returns_default(self):
        self.assertEqual(
            _coerce_setting_int({"k": "abc"}, "k", 7),
            7,
        )

    def test_none_value_returns_default(self):
        self.assertEqual(
            _coerce_setting_int({"k": None}, "k", 5),
            5,
        )


class CoerceSettingFloatTests(SimpleTestCase):
    """Verify float coercion from a bulk-loaded raw map."""

    def test_missing_key_returns_default(self):
        self.assertEqual(_coerce_setting_float({}, "missing", 0.5), 0.5)

    def test_valid_float(self):
        self.assertEqual(
            _coerce_setting_float({"k": "0.85"}, "k", 0.0),
            0.85,
        )

    def test_int_string_works(self):
        # int strings should coerce to float without issue.
        self.assertEqual(
            _coerce_setting_float({"k": "5"}, "k", 0.0),
            5.0,
        )

    def test_invalid_string_returns_default(self):
        self.assertEqual(
            _coerce_setting_float({"k": "not-a-number"}, "k", 0.5),
            0.5,
        )


class EnsureModelOutputPathTests(TestCase):
    """Verify ``_ensure_model_output_path`` writes under MEDIA_ROOT."""

    def test_default_filename(self):
        path = _ensure_model_output_path("test_subdir")
        # Use os.sep so this passes on both POSIX (`/`) and Windows (`\`).
        self.assertTrue(path.endswith(os.path.join("test_subdir", "model.pkl")))

    def test_custom_filename(self):
        path = _ensure_model_output_path("test_subdir2", filename="weights.bin")
        self.assertTrue(
            path.endswith(os.path.join("test_subdir2", "weights.bin"))
        )


class MedianTests(SimpleTestCase):
    """Verify the median helper for anchor entropy stats."""

    def test_odd_count(self):
        self.assertEqual(_median([1.0, 2.0, 3.0]), 2.0)

    def test_even_count(self):
        self.assertEqual(_median([1.0, 2.0, 3.0, 4.0]), 2.5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            _median([])


class ComputeAnchorEntropyStatsTests(SimpleTestCase):
    """Verify median + MAD computation across anchor entropies."""

    def test_returns_three_values(self):
        # Use varied anchor lengths so bigram entropy varies.
        median, mad, n = _compute_anchor_entropy_stats(
            ["hello world", "test phrase", "different text"],
        )
        self.assertEqual(n, 3)
        self.assertGreater(median, 0.0)
        self.assertGreaterEqual(mad, 0.0)


class FmFeatureBuildTests(SimpleTestCase):
    """Verify FM feature/target construction from rows."""

    def test_approved_target_one(self):
        features, targets = _build_fm_features(
            [
                {
                    "score_semantic": 0.5,
                    "anchor_confidence": "high",
                    "status": "approved",
                },
            ]
        )
        self.assertEqual(targets, [1.0])
        self.assertIn("anchor_confidence=high", features[0])

    def test_rejected_target_zero(self):
        features, targets = _build_fm_features(
            [
                {"score_keyword": 0.3, "anchor_confidence": None, "status": "rejected"},
            ]
        )
        self.assertEqual(targets, [0.0])
        # None anchor_confidence becomes "none".
        self.assertIn("anchor_confidence=none", features[0])

    def test_missing_score_columns_default_zero(self):
        features, _ = _build_fm_features(
            [
                {"status": "approved"},
            ]
        )
        for col in _FM_SCORE_COLUMNS:
            self.assertEqual(features[0][col], 0.0)


class Node2VecEdgeTriplesTests(SimpleTestCase):
    """Verify Node2Vec edge-triple builder uses string keys + weights."""

    def test_string_keys_and_weights(self):
        graph = mock.Mock()
        graph.edges.return_value = [
            (1, 2, {"weight": 0.5}),
            (3, 4, {}),
            (5, 6, None),
        ]
        triples = _build_node2vec_edge_triples(graph)
        self.assertEqual(len(triples), 3)
        self.assertEqual(triples[0], ("1", "2", 0.5))
        self.assertEqual(triples[1], ("3", "4", 1.0))
        self.assertEqual(triples[2], ("5", "6", 1.0))


class SummarizeCascadeSnapshotsTests(SimpleTestCase):
    """Verify the cascade summary string."""

    def test_both_snapshots_present(self):
        review = mock.Mock(
            cascade_relevance={"a": 1, "b": 2},
            ips_weighted_ctr=[1, 2, 3],
            training_runs=5,
        )
        impression = mock.Mock(relevance={"x": 1}, sessions=10, observations=42)
        msg = _summarize_cascade_snapshots(review, impression)
        self.assertIn("review-queue Cascade: 2 dests", msg)
        self.assertIn("impression Cascade: 1 dests", msg)

    def test_both_none_uses_fallback_messages(self):
        msg = _summarize_cascade_snapshots(None, None)
        self.assertIn("insufficient history", msg)
        self.assertIn("cold-start", msg)


class SummarizePositionBiasSnapshotsTests(SimpleTestCase):
    """Verify the position-bias summary string."""

    def test_both_snapshots(self):
        cascade = mock.Mock(ips_weighted_ctr=[1, 2, 3], training_runs=4)
        eta = mock.Mock(eta=1.234, observations=100)
        msg = _summarize_position_bias_snapshots(cascade, eta)
        self.assertIn("3 positions", msg)
        self.assertIn("η fit: 1.234", msg)
        self.assertIn("100 impressions", msg)

    def test_both_none(self):
        msg = _summarize_position_bias_snapshots(None, None)
        self.assertIn("insufficient review history", msg)
        self.assertIn("cold-start", msg)


class ReadMetaHpoAppliedAtTests(TestCase):
    """Verify the meta-HPO timestamp reader."""

    def setUp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key="meta_hpo.applied_at").delete()

    def test_no_value_returns_none(self):
        checkpoint = mock.Mock()
        result = _read_meta_hpo_applied_at(checkpoint)
        self.assertIsNone(result)
        checkpoint.assert_called_once()
        # Should report the no-prior-apply message.
        kwargs = checkpoint.call_args.kwargs
        self.assertIn("nothing to watch", kwargs["message"])

    def test_valid_iso_timestamp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.create(
            key="meta_hpo.applied_at",
            value="2026-05-01T12:00:00",
            value_type="str",
        )
        checkpoint = mock.Mock()
        result = _read_meta_hpo_applied_at(checkpoint)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_malformed_timestamp_returns_none(self):
        from apps.core.models import AppSetting

        AppSetting.objects.create(
            key="meta_hpo.applied_at",
            value="not-a-date",
            value_type="str",
        )
        checkpoint = mock.Mock()
        result = _read_meta_hpo_applied_at(checkpoint)
        self.assertIsNone(result)
        kwargs = checkpoint.call_args.kwargs
        self.assertIn("Malformed", kwargs["message"])


class ConstantSanityTests(SimpleTestCase):
    """Sanity bounds for the documented thresholds."""

    def test_kenlm_min_corpus_lines_positive(self):
        self.assertGreater(_KENLM_MIN_CORPUS_LINES, 0)

    def test_kenlm_min_sentence_chars_positive(self):
        self.assertGreater(_KENLM_MIN_SENTENCE_CHARS, 0)

    def test_lda_min_document_count_positive(self):
        self.assertGreater(_LDA_MIN_DOCUMENT_COUNT, 0)

    def test_lda_min_token_length_positive(self):
        self.assertGreater(_LDA_MIN_TOKEN_LENGTH, 0)

    def test_anchor_stats_min_meets_iglewicz_hoaglin(self):
        # The Iglewicz-Hoaglin 1993 §3.2 minimum sample size for stable
        # median/MAD estimates is N >= 30.
        self.assertGreaterEqual(_ANCHOR_STATS_MIN_ANCHORS, 30)

    def test_fm_min_training_rows_positive(self):
        self.assertGreater(_FM_MIN_TRAINING_ROWS, 0)

    def test_fm_lookback_days_one_quarter(self):
        # Match the IPS / Cascade producers per the production comment.
        self.assertEqual(_FM_FEEDBACK_LOOKBACK_DAYS, 90)
