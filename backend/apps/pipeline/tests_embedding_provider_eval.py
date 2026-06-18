"""Tests for embedding provider champion decisions."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.embedding_provider_eval import (
    ProviderScore,
    decide_provider_verdicts,
    paired_permutation_p_value,
)


class PairedPermutationTests(SimpleTestCase):
    def test_when_samples_match_then_p_value_is_one(self) -> None:
        self.assertEqual(
            paired_permutation_p_value([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
            1.0,
        )

    def test_when_challenger_always_wins_then_p_value_is_small(self) -> None:
        p_value = paired_permutation_p_value(
            [0.95, 0.9, 0.85, 0.8, 0.75, 0.7],
            [0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
        )
        self.assertLessEqual(p_value, 0.05)


class ProviderVerdictTests(SimpleTestCase):
    def test_when_challenger_wins_significantly_then_verdict_promotes(self) -> None:
        rows = [
            ProviderScore(
                "openai",
                ndcg_at_10=0.2,
                query_scores=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3),
            ),
            ProviderScore(
                "gemini",
                ndcg_at_10=0.8,
                query_scores=(0.95, 0.9, 0.85, 0.8, 0.75, 0.7),
            ),
        ]
        verdicts = decide_provider_verdicts(rows, champion_provider="openai")

        self.assertEqual(verdicts["gemini"].verdict, "promote")
        self.assertEqual(verdicts["gemini"].compared_to, "openai")
        self.assertFalse(verdicts["openai"].is_banned)

    def test_when_provider_loses_twice_then_provider_is_banned(self) -> None:
        rows = [
            ProviderScore(
                "openai",
                ndcg_at_10=0.9,
                query_scores=(0.95, 0.9, 0.85, 0.8, 0.75, 0.7),
            ),
            ProviderScore(
                "gemini",
                ndcg_at_10=0.1,
                query_scores=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3),
            ),
        ]
        verdicts = decide_provider_verdicts(
            rows,
            champion_provider="openai",
            existing_loss_counts={"gemini": 1},
        )

        self.assertEqual(verdicts["gemini"].verdict, "loss")
        self.assertEqual(verdicts["gemini"].loss_count, 2)
        self.assertTrue(verdicts["gemini"].is_banned)
