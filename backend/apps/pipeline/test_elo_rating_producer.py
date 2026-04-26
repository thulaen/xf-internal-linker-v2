"""Tests for pick #35 Elo end-to-end wiring.

Two layers:

1. **Pair derivation** — synthetic Suggestion-status history is
   converted to :class:`PairwiseOutcome` rows correctly. Cold-start
   (no reviewed history) yields zero pairs without raising.
2. **Refresh** — running ``fit_and_persist_from_history`` updates
   ``ContentItem.elo_rating`` for the destinations that competed,
   leaves un-competed destinations at 1500, and is idempotent under
   the no-history case.

The pair derivation logic is the place a new ``Impression`` model
(when added) would plug in — these tests pin the contract so the
producer keeps producing :class:`PairwiseOutcome` rows and the
consumer keeps receiving them, regardless of which input source.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.elo_rating import (
    DEFAULT_INITIAL_RATING,
)
from apps.pipeline.services.elo_rating_producer import (
    derive_pairs_from_suggestion_history,
    fit_and_persist_from_history,
)


class _Fixture:
    """Shared setup for the Elo producer tests."""

    @staticmethod
    def make_scope() -> ScopeItem:
        return ScopeItem.objects.create(
            scope_id=35, scope_type="node", title="elo-test"
        )

    @staticmethod
    def make_destination(scope: ScopeItem, content_id: int) -> ContentItem:
        return ContentItem.objects.create(
            content_id=content_id,
            content_type="thread",
            title=f"Dest {content_id}",
            scope=scope,
        )

    @staticmethod
    def make_host_sentence(scope: ScopeItem, content_id: int) -> Sentence:
        host = ContentItem.objects.create(
            content_id=content_id,
            content_type="thread",
            title=f"Host {content_id}",
            scope=scope,
        )
        post = Post.objects.create(content_item=host, raw_bbcode="x", clean_text="x")
        return Sentence.objects.create(
            content_item=host,
            post=post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )


class DerivePairsTests(TestCase):
    def setUp(self) -> None:
        self.scope = _Fixture.make_scope()

    def test_no_suggestions_returns_no_pairs(self) -> None:
        """Cold-start path."""
        pairs = list(derive_pairs_from_suggestion_history())
        self.assertEqual(pairs, [])

    def test_single_suggestion_per_host_yields_no_pairs(self) -> None:
        """A bucket of one cannot form a pair."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3500)
        dest = _Fixture.make_destination(self.scope, content_id=3501)
        run = PipelineRun.objects.create()
        Suggestion.objects.create(
            pipeline_run=run,
            destination=dest,
            host=host_sentence.content_item,
            host_sentence=host_sentence,
            destination_title="x",
            host_sentence_text="x",
            anchor_phrase="a",
            anchor_start=0,
            anchor_end=1,
            anchor_confidence="strong",
            score_final=0.5,
            status="approved",
        )
        self.assertEqual(list(derive_pairs_from_suggestion_history()), [])

    def test_approve_vs_reject_yields_winner(self) -> None:
        """Same host sentence; A approved, B rejected → A beats B."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3510)
        a = _Fixture.make_destination(self.scope, content_id=3511)
        b = _Fixture.make_destination(self.scope, content_id=3512)
        run = PipelineRun.objects.create()
        for dest, status in ((a, "approved"), (b, "rejected")):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host_sentence.content_item,
                host_sentence=host_sentence,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status=status,
            )

        pairs = list(derive_pairs_from_suggestion_history())
        self.assertEqual(len(pairs), 1)
        # Order of (a, b) vs (b, a) depends on insertion order, but
        # the score must be 1.0 (A=approved beat B=rejected) or 0.0
        # (B beat A) — never 0.5.
        outcome = pairs[0]
        self.assertIn(outcome.score_a, (0.0, 1.0))
        if outcome.item_a == (a.pk, "thread"):
            self.assertEqual(outcome.score_a, 1.0)
        else:
            self.assertEqual(outcome.item_a, (b.pk, "thread"))
            self.assertEqual(outcome.score_a, 0.0)

    def test_both_approved_yields_draw(self) -> None:
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3520)
        a = _Fixture.make_destination(self.scope, content_id=3521)
        b = _Fixture.make_destination(self.scope, content_id=3522)
        run = PipelineRun.objects.create()
        for dest in (a, b):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host_sentence.content_item,
                host_sentence=host_sentence,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status="approved",
            )

        pairs = list(derive_pairs_from_suggestion_history())
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].score_a, 0.5)

    def test_both_rejected_yields_no_pair(self) -> None:
        """Both rejected → no ordering signal → skipped."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3530)
        a = _Fixture.make_destination(self.scope, content_id=3531)
        b = _Fixture.make_destination(self.scope, content_id=3532)
        run = PipelineRun.objects.create()
        for dest in (a, b):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host_sentence.content_item,
                host_sentence=host_sentence,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status="rejected",
            )

        self.assertEqual(list(derive_pairs_from_suggestion_history()), [])

    def test_lookback_excludes_old_suggestions(self) -> None:
        """Suggestions outside the 90-day window are excluded."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3540)
        a = _Fixture.make_destination(self.scope, content_id=3541)
        b = _Fixture.make_destination(self.scope, content_id=3542)
        run = PipelineRun.objects.create()
        for dest, status in ((a, "approved"), (b, "rejected")):
            s = Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host_sentence.content_item,
                host_sentence=host_sentence,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status=status,
            )
            # Bypass auto_now to age the row past the lookback window.
            Suggestion.objects.filter(pk=s.pk).update(
                updated_at=timezone.now() - timedelta(days=120)
            )

        # Default lookback is 90 days → these 120-day-old rows excluded.
        self.assertEqual(list(derive_pairs_from_suggestion_history()), [])
        # 200-day lookback picks them up.
        pairs = list(derive_pairs_from_suggestion_history(days_lookback=200))
        self.assertEqual(len(pairs), 1)


class FitAndPersistTests(TestCase):
    def setUp(self) -> None:
        self.scope = _Fixture.make_scope()

    def test_no_history_leaves_ratings_at_initial(self) -> None:
        """Cold start: no pairs → all destinations stay at 1500."""
        a = _Fixture.make_destination(self.scope, content_id=3601)
        b = _Fixture.make_destination(self.scope, content_id=3602)

        result = fit_and_persist_from_history()
        self.assertEqual(result.pairs_processed, 0)
        self.assertEqual(result.destinations_rated, 0)

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.elo_rating, DEFAULT_INITIAL_RATING)
        self.assertEqual(b.elo_rating, DEFAULT_INITIAL_RATING)

    def test_single_match_updates_both_destinations(self) -> None:
        """An approve-vs-reject pair shifts both ratings (A up, B down)."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host_sentence = _Fixture.make_host_sentence(self.scope, content_id=3610)
        a = _Fixture.make_destination(self.scope, content_id=3611)
        b = _Fixture.make_destination(self.scope, content_id=3612)
        run = PipelineRun.objects.create()
        for dest, status in ((a, "approved"), (b, "rejected")):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host_sentence.content_item,
                host_sentence=host_sentence,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status=status,
            )

        result = fit_and_persist_from_history()
        self.assertEqual(result.pairs_processed, 1)
        self.assertEqual(result.destinations_rated, 2)

        a.refresh_from_db()
        b.refresh_from_db()
        # Conservation: in a draw-free pair, the K-factor delta moves
        # the winner's rating up and the loser's down by the same
        # amount (the helper enforces this in update()).
        self.assertGreater(a.elo_rating, DEFAULT_INITIAL_RATING)
        self.assertLess(b.elo_rating, DEFAULT_INITIAL_RATING)
        # Sum is conserved (within floating-point rounding) when both
        # start at the initial rating.
        self.assertAlmostEqual(
            a.elo_rating + b.elo_rating,
            2 * DEFAULT_INITIAL_RATING,
            places=4,
        )

    def test_existing_ratings_preserved_across_refresh(self) -> None:
        """A second refresh continues from the previous state, not from 1500."""
        from apps.suggestions.models import PipelineRun, Suggestion

        host = _Fixture.make_host_sentence(self.scope, content_id=3620)
        a = _Fixture.make_destination(self.scope, content_id=3621)
        b = _Fixture.make_destination(self.scope, content_id=3622)
        run = PipelineRun.objects.create()
        for dest, status in ((a, "approved"), (b, "rejected")):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host.content_item,
                host_sentence=host,
                destination_title="x",
                host_sentence_text="x",
                anchor_phrase="a",
                anchor_start=0,
                anchor_end=1,
                anchor_confidence="strong",
                score_final=0.5,
                status=status,
            )
        # First run.
        fit_and_persist_from_history()
        a.refresh_from_db()
        a_rating_after_first = a.elo_rating
        self.assertGreater(a_rating_after_first, DEFAULT_INITIAL_RATING)

        # Second run with no new pairs (the same suggestions are
        # re-paired, so A wins again). Ratings should drift further.
        fit_and_persist_from_history()
        a.refresh_from_db()
        self.assertGreater(a.elo_rating, a_rating_after_first)
