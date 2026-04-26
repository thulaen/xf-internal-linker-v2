"""Tests for W3b — feedback_relevance service (picks #33 + #34 wiring)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.pipeline.services import feedback_relevance
from apps.pipeline.services.cascade_click_model import ClickSession
from apps.pipeline.services.feedback_relevance import (
    KEY_CASCADE_RELEVANCE,
    KEY_IPS_CTR,
    cascade_relevance_for,
    compute_and_persist,
    load_snapshot,
)


class LoadSnapshotTests(TestCase):
    def test_cold_start_returns_none(self) -> None:
        self.assertIsNone(load_snapshot())

    def test_returns_snapshot_after_persist(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_CASCADE_RELEVANCE,
            defaults={
                "value": '{"42": 0.8, "99": 0.3}',
                "description": "",
            },
        )
        AppSetting.objects.update_or_create(
            key=KEY_IPS_CTR,
            defaults={"value": '{"1": 0.4, "2": 0.2}', "description": ""},
        )
        snap = load_snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.cascade_relevance[42], 0.8)
        self.assertEqual(snap.ips_weighted_ctr[1], 0.4)


class CascadeRelevanceForTests(TestCase):
    def test_cold_start_returns_neutral(self) -> None:
        self.assertEqual(cascade_relevance_for(42), 0.5)

    def test_lookup_returns_persisted_value(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_CASCADE_RELEVANCE,
            defaults={"value": '{"42": 0.85}', "description": ""},
        )
        self.assertAlmostEqual(cascade_relevance_for(42), 0.85)

    def test_unknown_destination_returns_neutral(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_CASCADE_RELEVANCE,
            defaults={"value": '{"42": 0.85}', "description": ""},
        )
        self.assertEqual(cascade_relevance_for(99), 0.5)


class ComputeAndPersistTests(TestCase):
    def test_returns_none_when_history_too_small(self) -> None:
        # Empty review history → not enough runs to fit.
        result = compute_and_persist()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_persists_snapshot_with_synthetic_runs(self) -> None:
        # Build synthetic Cascade sessions and a per-position event
        # table. Mock _build_observations to bypass the full ORM
        # fixture chain (PipelineRun + Suggestion + ContentItem +
        # Sentence is too much for a unit test focused on the
        # aggregation arithmetic).
        sessions = [
            ClickSession(ranked_docs=[1, 2, 3], clicked_rank=2),
            ClickSession(ranked_docs=[2, 3, 1], clicked_rank=1),
            ClickSession(ranked_docs=[1, 3, 2], clicked_rank=3),
            ClickSession(ranked_docs=[1, 2, 3], clicked_rank=2),
            ClickSession(ranked_docs=[2, 1, 3], clicked_rank=None),
            ClickSession(ranked_docs=[3, 1, 2], clicked_rank=2),
        ]
        position_events = {
            1: [True, True, False, False, True, False],
            2: [False, True, True, True, False, True],
            3: [False, False, False, True, False, False],
        }
        with patch.object(
            feedback_relevance,
            "_build_observations",
            return_value=(sessions, position_events),
        ):
            snapshot = compute_and_persist()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.training_runs, len(sessions))
        # Every destination that appeared in at least one session
        # should have a persisted relevance.
        self.assertEqual(set(snapshot.cascade_relevance.keys()), {1, 2, 3})
        # Round-trip via load_snapshot.
        loaded = load_snapshot()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.training_runs, len(sessions))


class ConsumerWireTests(TestCase):
    """Group A.4 — consumer wiring: producer outputs flow to consumers."""

    def test_cascade_relevance_for_prefers_impression_table(self) -> None:
        """When the impression-based table is populated, it wins."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.cascade_click_em_producer import (
            KEY_RELEVANCE as IMPRESSION_KEY_RELEVANCE,
        )

        # Both tables populated with conflicting values for dest 42.
        AppSetting.objects.update_or_create(
            key=KEY_CASCADE_RELEVANCE,
            defaults={"value": '{"42": 0.3}', "description": ""},
        )
        AppSetting.objects.update_or_create(
            key=IMPRESSION_KEY_RELEVANCE,
            defaults={"value": '{"42": 0.9}', "description": ""},
        )
        # Impression-based wins.
        self.assertAlmostEqual(cascade_relevance_for(42), 0.9)

    def test_cascade_relevance_falls_back_to_review_when_impression_missing(self) -> None:
        """Impression table populated but missing this dest → review-queue."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.cascade_click_em_producer import (
            KEY_RELEVANCE as IMPRESSION_KEY_RELEVANCE,
        )

        AppSetting.objects.update_or_create(
            key=KEY_CASCADE_RELEVANCE,
            defaults={"value": '{"42": 0.65}', "description": ""},
        )
        # Impression table has *some* dest but not 42.
        AppSetting.objects.update_or_create(
            key=IMPRESSION_KEY_RELEVANCE,
            defaults={"value": '{"99": 0.9}', "description": ""},
        )
        self.assertAlmostEqual(cascade_relevance_for(42), 0.65)

    def test_cascade_relevance_neutral_when_both_empty(self) -> None:
        """No producer has run yet → neutral 0.5."""
        self.assertAlmostEqual(cascade_relevance_for(42), 0.5)

    def test_compute_ips_ctr_reads_fitted_eta(self) -> None:
        """When η is persisted, _compute_ips_ctr uses it instead of 1.0."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.feedback_relevance import _compute_ips_ctr
        from apps.pipeline.services.position_bias_ips import (
            DEFAULT_MAX_WEIGHT,
            ips_weight,
        )
        from apps.pipeline.services.position_bias_ips_producer import KEY_ETA

        # Persist a fitted η of 0.5 (different from the default 1.0).
        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "0.5", "description": ""}
        )
        # All-approved at position 4 → CTR 1.0 × IPS weight at η=0.5.
        # ips_weight(4, eta=0.5) = 4^0.5 = 2.0; with eta=1.0 it would
        # be 4.0. Difference proves the fitted value was used.
        events = {4: [True, True, True, True]}
        result = _compute_ips_ctr(events)
        expected = 1.0 * ips_weight(
            position=4, eta=0.5, max_weight=DEFAULT_MAX_WEIGHT
        )
        self.assertAlmostEqual(result[4], expected)
        self.assertAlmostEqual(result[4], 2.0)

    def test_compute_ips_ctr_uses_default_eta_on_cold_start(self) -> None:
        """No fitted η persisted → falls back to the helper's default."""
        from apps.pipeline.services.feedback_relevance import _compute_ips_ctr
        from apps.pipeline.services.position_bias_ips import (
            DEFAULT_MAX_WEIGHT,
            DEFAULT_POWER_LAW_ETA,
            ips_weight,
        )

        events = {4: [True, True, True, True]}
        result = _compute_ips_ctr(events)
        expected = 1.0 * ips_weight(
            position=4,
            eta=DEFAULT_POWER_LAW_ETA,
            max_weight=DEFAULT_MAX_WEIGHT,
        )
        self.assertAlmostEqual(result[4], expected)
        self.assertAlmostEqual(result[4], 4.0)
