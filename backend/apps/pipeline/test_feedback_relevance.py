"""Tests for W3b — feedback_relevance service (picks #33 + #34 wiring)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.pipeline.services import feedback_relevance
from apps.pipeline.services.cascade_click_model import ClickSession
from apps.pipeline.services.feedback_relevance import (
    KEY_CASCADE_RELEVANCE,
    KEY_IPS_CTR,
    MIN_PIPELINE_RUNS,
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
