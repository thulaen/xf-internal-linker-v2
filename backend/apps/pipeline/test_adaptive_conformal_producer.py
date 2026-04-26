"""Tests for pick #52 Adaptive Conformal Inference end-to-end wiring."""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.adaptive_conformal_inference import (
    DEFAULT_CLIP_MAX,
    DEFAULT_CLIP_MIN,
    DEFAULT_TARGET_ALPHA,
)
from apps.pipeline.services.adaptive_conformal_producer import (
    load_alpha,
    update_alpha_from_recent_outcomes,
)


class AciProducerTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun

        self.scope = ScopeItem.objects.create(
            scope_id=52, scope_type="node", title="aci-test"
        )
        self.host = ContentItem.objects.create(
            content_id=5200, content_type="thread", title="host", scope=self.scope
        )
        self.host_post = Post.objects.create(
            content_item=self.host, raw_bbcode="x", clean_text="x"
        )
        self.host_sentence = Sentence.objects.create(
            content_item=self.host,
            post=self.host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        self.dest = ContentItem.objects.create(
            content_id=5201, content_type="thread", title="dest", scope=self.scope
        )
        self.run = PipelineRun.objects.create()

    def _seed_reviewed(self, *, score: float, status: str, lower: float, upper: float):
        from apps.suggestions.models import Suggestion

        return Suggestion.objects.create(
            pipeline_run=self.run,
            destination=self.dest,
            host=self.host,
            host_sentence=self.host_sentence,
            destination_title="dest",
            host_sentence_text="A host sentence.",
            anchor_phrase="anchor",
            anchor_start=0,
            anchor_end=6,
            anchor_confidence="strong",
            score_final=score,
            status=status,
            confidence_lower_bound=lower,
            confidence_upper_bound=upper,
        )

    def test_load_alpha_cold_start_returns_target(self) -> None:
        self.assertEqual(load_alpha(), DEFAULT_TARGET_ALPHA)

    def test_no_outcomes_keeps_alpha_at_target(self) -> None:
        """Empty pool → α stays at the static target."""
        result = update_alpha_from_recent_outcomes()
        self.assertEqual(result.observations_processed, 0)
        self.assertEqual(result.current_alpha, DEFAULT_TARGET_ALPHA)
        # And it persists.
        self.assertEqual(load_alpha(), DEFAULT_TARGET_ALPHA)

    def test_undercoverage_widens_alpha(self) -> None:
        """Many in-band misses → α grows (toward clip_max)."""
        # All-positive labels with bounds that DON'T contain 1.0 →
        # every observation is "not covered" → observed_miscoverage=1.0
        # → delta=1.0 - target=0.9 (positive) → α grows.
        # The ACI helper has a warmup of window_size//2 — feed enough
        # rows to clear it.
        from apps.pipeline.services.adaptive_conformal_inference import (
            DEFAULT_WINDOW_SIZE,
        )

        for _ in range(DEFAULT_WINDOW_SIZE):
            self._seed_reviewed(
                score=0.5, status="approved", lower=0.4, upper=0.6
            )
        # label=1.0 falls outside [0.4, 0.6] → not covered.
        result = update_alpha_from_recent_outcomes()
        self.assertGreater(result.observations_processed, 0)
        self.assertGreater(result.current_alpha, DEFAULT_TARGET_ALPHA)
        self.assertLessEqual(result.current_alpha, DEFAULT_CLIP_MAX)

    def test_overcoverage_shrinks_alpha(self) -> None:
        """Wide bands always covering → α shrinks (toward clip_min)."""
        from apps.pipeline.services.adaptive_conformal_inference import (
            DEFAULT_WINDOW_SIZE,
        )

        # Bounds [-1, 2] always contain 0 and 1 → always covered.
        for _ in range(DEFAULT_WINDOW_SIZE):
            self._seed_reviewed(
                score=0.5, status="approved", lower=-1.0, upper=2.0
            )
        result = update_alpha_from_recent_outcomes()
        self.assertGreater(result.observations_processed, 0)
        self.assertLess(result.current_alpha, DEFAULT_TARGET_ALPHA)
        self.assertGreaterEqual(result.current_alpha, DEFAULT_CLIP_MIN)

    def test_alpha_clamped_within_clip_bounds(self) -> None:
        """A single update never escapes the [clip_min, clip_max] band."""
        from apps.pipeline.services.adaptive_conformal_inference import (
            DEFAULT_WINDOW_SIZE,
        )

        for _ in range(DEFAULT_WINDOW_SIZE):
            self._seed_reviewed(
                score=0.5, status="approved", lower=0.4, upper=0.6
            )
        result = update_alpha_from_recent_outcomes()
        self.assertGreaterEqual(result.current_alpha, DEFAULT_CLIP_MIN)
        self.assertLessEqual(result.current_alpha, DEFAULT_CLIP_MAX)
