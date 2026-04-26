"""Tests for PR-N feedback / click / rating helpers."""

from __future__ import annotations

import math

from django.test import SimpleTestCase

from apps.pipeline.services.cascade_click_model import (
    ClickSession,
    estimate as cascade_estimate,
    prior_mean,
)
from apps.pipeline.services.elo_rating import (
    DEFAULT_INITIAL_RATING,
    EloState,
    PairwiseOutcome,
    expected_score,
    run_batch,
    update as elo_update,
)
from apps.pipeline.services.ema_aggregator import (
    EMASummary,
    alpha_from_half_life,
    ema,
    ema_per_key,
)
from apps.pipeline.services.position_bias_ips import (
    DEFAULT_POWER_LAW_ETA,
    InterventionLog,
    average_reweighted_click_rate,
    fit_eta_from_interventions,
    ips_weight,
    power_law_propensity,
    reweight_clicks,
)


# ── EMA ─────────────────────────────────────────────────────────────


class EMATests(SimpleTestCase):
    def test_single_observation_returned_unchanged(self) -> None:
        summary = ema([5.0])
        self.assertEqual(summary.final_value, 5.0)
        self.assertEqual(summary.observation_count, 1)

    def test_converges_toward_steady_input(self) -> None:
        summary = ema([3.0] * 500, alpha=0.1)
        self.assertAlmostEqual(summary.final_value, 3.0, places=5)

    def test_recent_spike_pulls_value_up(self) -> None:
        base = ema([1.0] * 100, alpha=0.3)
        spiked = ema([1.0] * 99 + [10.0], alpha=0.3)
        self.assertGreater(spiked.final_value, base.final_value)

    def test_seed_supports_carrying_state(self) -> None:
        first = ema([1.0, 1.0, 1.0], alpha=0.5)
        continued = ema([2.0, 2.0], alpha=0.5, seed=first.final_value)
        # Continued should lie between the seed (1.0) and the new input (2.0).
        self.assertGreater(continued.final_value, 1.0)
        self.assertLess(continued.final_value, 2.0)

    def test_bad_alpha_rejected(self) -> None:
        for bad in (0.0, -0.1, 1.5):
            with self.assertRaises(ValueError):
                ema([1.0], alpha=bad)

    def test_empty_series_returns_zero_count(self) -> None:
        summary = ema([])
        self.assertEqual(summary.observation_count, 0)

    def test_alpha_from_half_life_7_steps(self) -> None:
        alpha = alpha_from_half_life(7)
        # After 7 steps, the effective weight of the starting value
        # should be ~0.5.
        weight_after_7 = math.pow(1.0 - alpha, 7)
        self.assertAlmostEqual(weight_after_7, 0.5, places=4)

    def test_alpha_from_half_life_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            alpha_from_half_life(0)
        with self.assertRaises(ValueError):
            alpha_from_half_life(-3)

    def test_ema_per_key_independent(self) -> None:
        out = ema_per_key({"a": [1.0, 1.0, 1.0], "b": [10.0]})
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.assertIsInstance(out["a"], EMASummary)


# ── Cascade Click Model ────────────────────────────────────────────


class CascadeClickTests(SimpleTestCase):
    def test_click_boosts_relevance(self) -> None:
        sessions = [
            ClickSession(ranked_docs=["a", "b"], clicked_rank=1),
            ClickSession(ranked_docs=["a", "b"], clicked_rank=1),
            ClickSession(ranked_docs=["a", "b"], clicked_rank=None),
        ]
        rel = cascade_estimate(sessions)
        self.assertGreater(rel["a"].relevance, rel["b"].relevance)

    def test_only_examined_positions_tracked(self) -> None:
        sessions = [
            ClickSession(ranked_docs=["a", "b", "c"], clicked_rank=1),
        ]
        rel = cascade_estimate(sessions)
        # Click at rank 1 ⇒ b and c never examined.
        self.assertIn("a", rel)
        self.assertNotIn("b", rel)
        self.assertNotIn("c", rel)

    def test_no_click_means_full_scan(self) -> None:
        sessions = [
            ClickSession(ranked_docs=["a", "b", "c"], clicked_rank=None),
        ]
        rel = cascade_estimate(sessions)
        # All three examined; none clicked → smoothed rel near 0 but > 0.
        for doc in ("a", "b", "c"):
            self.assertGreater(rel[doc].relevance, 0.0)
            self.assertLess(rel[doc].relevance, 0.5)

    def test_out_of_range_click_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cascade_estimate(
                [ClickSession(ranked_docs=["a"], clicked_rank=5)]
            )

    def test_prior_mean_uniform_default(self) -> None:
        self.assertAlmostEqual(prior_mean(), 0.5)

    def test_smoothing_prior_prevents_zero_rel(self) -> None:
        # One session, no click → smoothed rel > 0 thanks to α prior.
        sessions = [ClickSession(ranked_docs=["a"], clicked_rank=None)]
        rel = cascade_estimate(sessions)
        self.assertGreater(rel["a"].relevance, 0.0)


# ── Position Bias / IPS ────────────────────────────────────────────


class PositionBiasIPSTests(SimpleTestCase):
    def test_power_law_propensity_monotone_decreasing(self) -> None:
        for pos in range(1, 10):
            self.assertGreater(
                power_law_propensity(pos),
                power_law_propensity(pos + 1),
            )

    def test_position_one_has_propensity_one(self) -> None:
        self.assertEqual(power_law_propensity(1), 1.0)

    def test_bad_position_rejected(self) -> None:
        with self.assertRaises(ValueError):
            power_law_propensity(0)

    def test_ips_weight_clipped(self) -> None:
        weight = ips_weight(position=100, max_weight=5.0)
        self.assertLessEqual(weight, 5.0)

    def test_reweight_clicks_scales_deeper_positions_more(self) -> None:
        raw = {1: 10, 10: 10}
        out = reweight_clicks(raw)
        self.assertGreater(out[10], out[1])

    def test_average_reweighted_ctr_produces_finite(self) -> None:
        events = [(1, True), (1, False), (5, True), (10, False)]
        rate = average_reweighted_click_rate(click_events=events)
        self.assertTrue(math.isfinite(rate))
        self.assertGreater(rate, 0.0)

    def test_fit_eta_from_interventions_returns_positive(self) -> None:
        # Swap experiment: a clicked doc moved from pos 3 → pos 1
        # should fit an η that prefers near-top positions.
        logs = [
            InterventionLog(original_position=3, shown_position=1, clicked=True),
            InterventionLog(original_position=3, shown_position=1, clicked=True),
            InterventionLog(original_position=1, shown_position=3, clicked=False),
            InterventionLog(original_position=1, shown_position=3, clicked=False),
        ]
        eta = fit_eta_from_interventions(logs)
        self.assertGreater(eta, 0.1)

    def test_fit_eta_rejects_empty_logs(self) -> None:
        with self.assertRaises(ValueError):
            fit_eta_from_interventions([])

    def test_fit_eta_rejects_all_zero_clicks(self) -> None:
        logs = [
            InterventionLog(original_position=1, shown_position=2, clicked=False),
        ]
        with self.assertRaises(ValueError):
            fit_eta_from_interventions(logs)

    def test_default_eta_is_reasonable(self) -> None:
        self.assertGreater(DEFAULT_POWER_LAW_ETA, 0.5)
        self.assertLess(DEFAULT_POWER_LAW_ETA, 2.0)


# ── Elo ────────────────────────────────────────────────────────────


class EloRatingTests(SimpleTestCase):
    def test_equal_ratings_give_expected_half(self) -> None:
        self.assertAlmostEqual(
            expected_score(rating_a=1500, rating_b=1500),
            0.5,
        )

    def test_higher_rating_expected_above_half(self) -> None:
        self.assertGreater(
            expected_score(rating_a=1600, rating_b=1400),
            0.5,
        )

    def test_win_raises_and_loss_lowers(self) -> None:
        state = EloState()
        elo_update(
            state,
            PairwiseOutcome(item_a="X", item_b="Y", score_a=1.0),
        )
        self.assertGreater(state.get("X"), DEFAULT_INITIAL_RATING)
        self.assertLess(state.get("Y"), DEFAULT_INITIAL_RATING)

    def test_draw_is_noop_between_equal_ratings(self) -> None:
        state = EloState()
        elo_update(
            state,
            PairwiseOutcome(item_a="X", item_b="Y", score_a=0.5),
        )
        self.assertAlmostEqual(state.get("X"), DEFAULT_INITIAL_RATING)
        self.assertAlmostEqual(state.get("Y"), DEFAULT_INITIAL_RATING)

    def test_bad_score_rejected(self) -> None:
        with self.assertRaises(ValueError):
            elo_update(
                EloState(),
                PairwiseOutcome(item_a="a", item_b="b", score_a=1.5),
            )

    def test_run_batch_multiple_wins_grow_rating(self) -> None:
        outcomes = [
            PairwiseOutcome(item_a="champ", item_b=f"rival{i}", score_a=1.0)
            for i in range(10)
        ]
        state = run_batch(outcomes)
        self.assertGreater(state.get("champ"), DEFAULT_INITIAL_RATING + 100)
        self.assertEqual(state.match_counts["champ"], 10)

    def test_run_batch_continues_from_initial_state(self) -> None:
        state = EloState(ratings={"a": 1700.0, "b": 1700.0})
        run_batch(
            [PairwiseOutcome(item_a="a", item_b="b", score_a=1.0)],
            initial_state=state,
        )
        self.assertGreater(state.get("a"), 1700.0)
