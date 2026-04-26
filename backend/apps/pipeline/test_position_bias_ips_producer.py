"""Tests for pick #33 IPS Position Bias producer.

The producer reads ``SuggestionImpression`` rows, fits the η exponent
of the power-law propensity model (Joachims et al. 2017 §4), and
persists it to AppSetting. Consumers read η back via
:func:`load_eta` and feed it to ``position_bias_ips.ips_weight``.

These tests mirror ``test_adaptive_conformal_producer.py`` — same
fixture pattern, same cold-start-safe assertions.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.position_bias_ips import (
    DEFAULT_MAX_WEIGHT,
    DEFAULT_POWER_LAW_ETA,
)
from apps.pipeline.services.position_bias_ips_producer import (
    KEY_ETA,
    KEY_FITTED_AT,
    KEY_MAX_WEIGHT,
    KEY_OBSERVATIONS,
    MIN_IMPRESSIONS_FOR_FIT,
    fit_and_persist_from_impressions,
    ips_weight_for_position,
    load_eta,
    load_snapshot,
)


class _Fixture:
    """Shared Suggestion + SuggestionImpression seed."""

    @staticmethod
    def make_suggestion():
        from apps.suggestions.models import PipelineRun, Suggestion

        scope = ScopeItem.objects.create(scope_id=33, scope_type="node", title="ips")
        host = ContentItem.objects.create(
            content_id=3300, content_type="thread", title="host", scope=scope
        )
        host_post = Post.objects.create(
            content_item=host, raw_bbcode="x", clean_text="x"
        )
        host_sentence = Sentence.objects.create(
            content_item=host,
            post=host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        dest = ContentItem.objects.create(
            content_id=3301, content_type="thread", title="dest", scope=scope
        )
        run = PipelineRun.objects.create()
        return Suggestion.objects.create(
            pipeline_run=run,
            destination=dest,
            host=host,
            host_sentence=host_sentence,
            destination_title="dest",
            host_sentence_text="A host sentence.",
            anchor_phrase="anchor",
            anchor_start=0,
            anchor_end=6,
            anchor_confidence="strong",
            score_final=0.5,
            status="pending",
        )

    @staticmethod
    def seed_impressions(suggestion, *, position: int, count: int, click_rate: float):
        """Bulk-create ``count`` SuggestionImpression rows at *position*.

        ``click_rate`` is the fraction of rows where ``clicked=True``;
        deterministic (alternating) so tests don't flake on RNG.
        """
        from apps.suggestions.models import SuggestionImpression

        rows = []
        click_target = int(round(count * click_rate))
        for i in range(count):
            rows.append(
                SuggestionImpression(
                    suggestion=suggestion,
                    position=position,
                    clicked=(i < click_target),
                )
            )
        SuggestionImpression.objects.bulk_create(rows)


class LoadEtaTests(TestCase):
    def test_cold_start_returns_default(self) -> None:
        self.assertEqual(load_eta(), DEFAULT_POWER_LAW_ETA)

    def test_returns_persisted_value(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "1.42", "description": ""}
        )
        self.assertAlmostEqual(load_eta(), 1.42)

    def test_malformed_row_falls_back_to_default(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "not-a-number", "description": ""}
        )
        self.assertEqual(load_eta(), DEFAULT_POWER_LAW_ETA)

    def test_custom_default_used_on_cold_start(self) -> None:
        self.assertEqual(load_eta(default=0.7), 0.7)


class LoadSnapshotTests(TestCase):
    def test_cold_start_returns_none(self) -> None:
        self.assertIsNone(load_snapshot())

    def test_returns_snapshot_when_persisted(self) -> None:
        from apps.core.models import AppSetting

        for key, value in (
            (KEY_ETA, "1.05"),
            (KEY_MAX_WEIGHT, "8.0"),
            (KEY_OBSERVATIONS, "1234"),
            (KEY_FITTED_AT, "2026-04-25T13:00:00+00:00"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )
        snap = load_snapshot()
        self.assertIsNotNone(snap)
        self.assertAlmostEqual(snap.eta, 1.05)
        self.assertEqual(snap.max_weight, 8.0)
        self.assertEqual(snap.observations, 1234)
        self.assertEqual(snap.fitted_at, "2026-04-25T13:00:00+00:00")

    def test_partial_persist_falls_back_to_defaults(self) -> None:
        """Only the eta row is set — the other fields use sensible defaults."""
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "1.1", "description": ""}
        )
        snap = load_snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.max_weight, DEFAULT_MAX_WEIGHT)
        self.assertEqual(snap.observations, 0)
        self.assertIsNone(snap.fitted_at)


class IpsWeightForPositionTests(TestCase):
    def test_cold_start_uses_helper_default(self) -> None:
        # No persisted snapshot → ips_weight(position=1, eta=1.0) = 1.0
        self.assertAlmostEqual(ips_weight_for_position(1), 1.0)
        # ips_weight(position=4, eta=1.0) = 4.0
        self.assertAlmostEqual(ips_weight_for_position(4), 4.0)

    def test_uses_persisted_eta_when_snapshot_exists(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "0.5", "description": ""}
        )
        # ips_weight(position=4, eta=0.5) = 4^0.5 = 2.0
        self.assertAlmostEqual(ips_weight_for_position(4), 2.0)

    def test_max_weight_clip_applies(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_ETA, defaults={"value": "2.0", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key=KEY_MAX_WEIGHT, defaults={"value": "5.0", "description": ""}
        )
        # ips_weight(position=10, eta=2.0) = 100; clipped to 5.0
        self.assertAlmostEqual(ips_weight_for_position(10), 5.0)


class FitAndPersistTests(TestCase):
    def test_cold_start_no_impressions_returns_none(self) -> None:
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_below_minimum_impressions_returns_none(self) -> None:
        suggestion = _Fixture.make_suggestion()
        # Fewer than MIN_IMPRESSIONS_FOR_FIT rows.
        _Fixture.seed_impressions(suggestion, position=0, count=10, click_rate=0.5)
        _Fixture.seed_impressions(suggestion, position=1, count=10, click_rate=0.3)
        self.assertLess(20, MIN_IMPRESSIONS_FOR_FIT)
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        # Nothing persisted.
        self.assertIsNone(load_snapshot())

    def test_single_position_returns_none(self) -> None:
        """Degenerate: every impression at position 0 → no curve to fit."""
        suggestion = _Fixture.make_suggestion()
        # Above minimum but only one distinct position.
        _Fixture.seed_impressions(
            suggestion,
            position=0,
            count=MIN_IMPRESSIONS_FOR_FIT + 50,
            click_rate=0.5,
        )
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_persists_snapshot_with_realistic_data(self) -> None:
        """Multi-position click curve → η fits and persists cleanly."""
        suggestion = _Fixture.make_suggestion()
        # Synthesize a realistic click-by-position curve. Higher
        # positions get fewer clicks. ~250 rows total spread across
        # 5 positions clears the MIN_IMPRESSIONS_FOR_FIT bar.
        _Fixture.seed_impressions(suggestion, position=0, count=60, click_rate=0.50)
        _Fixture.seed_impressions(suggestion, position=1, count=60, click_rate=0.30)
        _Fixture.seed_impressions(suggestion, position=2, count=60, click_rate=0.15)
        _Fixture.seed_impressions(suggestion, position=3, count=40, click_rate=0.08)
        _Fixture.seed_impressions(suggestion, position=4, count=40, click_rate=0.04)
        result = fit_and_persist_from_impressions()
        self.assertIsNotNone(result)
        # The fitter is bounded to [0.1, 3.0] — anything inside there
        # is a valid fit; we don't assert a specific value because
        # the bounded scalar minimiser is sensitive to synthetic
        # likelihood landscapes.
        self.assertGreaterEqual(result.eta, 0.1)
        self.assertLessEqual(result.eta, 3.0)
        self.assertEqual(result.observations, 260)
        self.assertEqual(result.max_weight, DEFAULT_MAX_WEIGHT)
        self.assertIsNotNone(result.fitted_at)

        # Round-trip: load_eta returns the same value the producer
        # just persisted.
        self.assertAlmostEqual(load_eta(), result.eta)

    def test_idempotent_refit_overwrites_in_place(self) -> None:
        """Re-running on the same data updates AppSetting in place."""
        from apps.core.models import AppSetting

        suggestion = _Fixture.make_suggestion()
        _Fixture.seed_impressions(suggestion, position=0, count=60, click_rate=0.50)
        _Fixture.seed_impressions(suggestion, position=1, count=60, click_rate=0.20)
        _Fixture.seed_impressions(suggestion, position=2, count=80, click_rate=0.10)
        _Fixture.seed_impressions(suggestion, position=3, count=40, click_rate=0.05)
        first = fit_and_persist_from_impressions()
        rows_first = AppSetting.objects.filter(
            key__startswith="position_bias_ips."
        ).count()
        second = fit_and_persist_from_impressions()
        rows_second = AppSetting.objects.filter(
            key__startswith="position_bias_ips."
        ).count()
        self.assertEqual(rows_first, rows_second)
        # Same data → same η (within scipy's tolerance).
        self.assertAlmostEqual(first.eta, second.eta, places=5)

    def test_lookback_filter_drops_old_rows(self) -> None:
        """Rows older than ``days_lookback`` are excluded from the fit."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.suggestions.models import SuggestionImpression

        suggestion = _Fixture.make_suggestion()
        # Seed enough fresh rows so the producer would fit.
        _Fixture.seed_impressions(suggestion, position=0, count=120, click_rate=0.5)
        _Fixture.seed_impressions(suggestion, position=1, count=120, click_rate=0.3)
        # Now back-date them all to 200 days ago.
        old_cutoff = timezone.now() - timedelta(days=200)
        SuggestionImpression.objects.update(impressed_at=old_cutoff)

        # Default lookback is 90 days → all rows excluded → no fit.
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)

        # Wider lookback → rows now included → fit runs.
        result_wide = fit_and_persist_from_impressions(days_lookback=365)
        self.assertIsNotNone(result_wide)
