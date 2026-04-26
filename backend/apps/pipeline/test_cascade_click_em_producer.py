"""Tests for pick #34 Cascade Click Model producer.

Mirrors the structure of :mod:`apps.pipeline.test_position_bias_ips_producer`:
fixture builder, cold-start checks, threshold tests, and a
realistic-data round-trip.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.cascade_click_em_producer import (
    KEY_FITTED_AT,
    KEY_OBSERVATIONS,
    KEY_RELEVANCE,
    KEY_SESSIONS,
    MIN_IMPRESSIONS_FOR_FIT,
    MIN_SESSIONS_FOR_FIT,
    fit_and_persist_from_impressions,
    load_relevance_table,
    load_snapshot,
    relevance_for,
)
from apps.pipeline.services.cascade_click_model import prior_mean


class _Fixture:
    """Helper for building PipelineRun + Suggestion + Impression graphs."""

    @staticmethod
    def make_scope():
        return ScopeItem.objects.create(scope_id=34, scope_type="node", title="cascade")

    @staticmethod
    def make_content_item(*, scope, content_id: int, title: str):
        return ContentItem.objects.create(
            content_id=content_id,
            content_type="thread",
            title=title,
            scope=scope,
        )

    @staticmethod
    def make_host_with_sentence(scope, content_id: int):
        host = _Fixture.make_content_item(
            scope=scope, content_id=content_id, title=f"host-{content_id}"
        )
        post = Post.objects.create(content_item=host, raw_bbcode="x", clean_text="x")
        sentence = Sentence.objects.create(
            content_item=host,
            post=post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        return host, sentence

    @staticmethod
    def make_run_with_destinations(
        *,
        scope,
        host,
        host_sentence,
        run_index: int,
        destinations,
    ):
        """Build a PipelineRun with one Suggestion per destination."""
        from apps.suggestions.models import PipelineRun, Suggestion

        run = PipelineRun.objects.create()
        suggestions = []
        for offset, dest in enumerate(destinations):
            s = Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host,
                host_sentence=host_sentence,
                destination_title=f"dest-{run_index}-{offset}",
                host_sentence_text="A host sentence.",
                anchor_phrase="anchor",
                anchor_start=0,
                anchor_end=6,
                anchor_confidence="strong",
                score_final=0.5,
                status="pending",
            )
            suggestions.append(s)
        return run, suggestions

    @staticmethod
    def seed_session(*, suggestions, clicked_index: int | None):
        """Log impressions: each suggestion at its rank, click at index.

        ``suggestions`` is the rank-ordered list (index 0 = top).
        ``clicked_index`` is the 0-based index that gets clicked, or
        None if no click happened.
        """
        from apps.suggestions.models import SuggestionImpression

        rows = []
        for rank, sugg in enumerate(suggestions):
            rows.append(
                SuggestionImpression(
                    suggestion=sugg,
                    position=rank,
                    clicked=(clicked_index is not None and rank == clicked_index),
                )
            )
        SuggestionImpression.objects.bulk_create(rows)


class LoadAPITests(TestCase):
    def test_cold_start_returns_empty_table(self) -> None:
        self.assertEqual(load_relevance_table(), {})

    def test_cold_start_relevance_for_returns_prior_mean(self) -> None:
        self.assertAlmostEqual(relevance_for(123), prior_mean())

    def test_cold_start_snapshot_is_none(self) -> None:
        self.assertIsNone(load_snapshot())

    def test_returns_persisted_table(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_RELEVANCE,
            defaults={"value": '{"42": 0.85, "99": 0.10}', "description": ""},
        )
        table = load_relevance_table()
        self.assertAlmostEqual(table[42], 0.85)
        self.assertAlmostEqual(table[99], 0.10)
        # Look-up unknown destination → prior fallback.
        self.assertAlmostEqual(relevance_for(7), prior_mean())
        # Look-up known destination → persisted value.
        self.assertAlmostEqual(relevance_for(42), 0.85)

    def test_malformed_json_falls_back_to_empty(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=KEY_RELEVANCE,
            defaults={"value": "not-json", "description": ""},
        )
        self.assertEqual(load_relevance_table(), {})

    def test_load_snapshot_round_trip(self) -> None:
        from apps.core.models import AppSetting

        for key, value in (
            (KEY_RELEVANCE, '{"7": 0.8}'),
            (KEY_OBSERVATIONS, "500"),
            (KEY_SESSIONS, "30"),
            (KEY_FITTED_AT, "2026-04-25T13:00:00+00:00"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )
        snap = load_snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap.relevance[7], 0.8)
        self.assertEqual(snap.observations, 500)
        self.assertEqual(snap.sessions, 30)
        self.assertEqual(snap.fitted_at, "2026-04-25T13:00:00+00:00")


class FitAndPersistTests(TestCase):
    def test_cold_start_no_impressions_returns_none(self) -> None:
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_below_minimum_impressions_returns_none(self) -> None:
        scope = _Fixture.make_scope()
        host, sentence = _Fixture.make_host_with_sentence(scope, 1000)
        dests = [
            _Fixture.make_content_item(scope=scope, content_id=2000 + i, title=f"d{i}")
            for i in range(5)
        ]
        # Only 5 sessions × 5 impressions = 25 rows, well below the
        # 200-row minimum.
        for run_index in range(5):
            _, suggs = _Fixture.make_run_with_destinations(
                scope=scope,
                host=host,
                host_sentence=sentence,
                run_index=run_index,
                destinations=dests,
            )
            _Fixture.seed_session(suggestions=suggs, clicked_index=run_index % 5)
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_below_minimum_sessions_returns_none(self) -> None:
        """Many impressions but only 1 session → fit skipped."""
        scope = _Fixture.make_scope()
        host, sentence = _Fixture.make_host_with_sentence(scope, 1100)
        # 250 destinations all in a single pipeline_run → 250
        # impressions but 1 session.
        dests = [
            _Fixture.make_content_item(scope=scope, content_id=3000 + i, title=f"d{i}")
            for i in range(MIN_IMPRESSIONS_FOR_FIT + 50)
        ]
        _, suggs = _Fixture.make_run_with_destinations(
            scope=scope,
            host=host,
            host_sentence=sentence,
            run_index=0,
            destinations=dests,
        )
        _Fixture.seed_session(suggestions=suggs, clicked_index=0)
        result = fit_and_persist_from_impressions()
        self.assertIsNone(result)
        self.assertIsNone(load_snapshot())

    def test_persists_snapshot_with_realistic_data(self) -> None:
        """Many sessions × many positions → cascade fits cleanly."""
        scope = _Fixture.make_scope()
        host, sentence = _Fixture.make_host_with_sentence(scope, 1200)
        # 10 destinations shared across all sessions.
        dests = [
            _Fixture.make_content_item(scope=scope, content_id=4000 + i, title=f"d{i}")
            for i in range(10)
        ]
        # 30 sessions × 10 impressions = 300 rows. Make dest 0 the
        # clear winner (clicked in 8/10 sessions), with a few clicks
        # on dest 1 and dest 2 to provide examination evidence for
        # those positions. Rank 0 is examined every session, so to
        # push its relevance above the prior 0.5 it needs more
        # clicks than non-clicks — 8/10 yields ~0.81 after
        # Laplace smoothing.
        click_pattern = [0, 0, 0, 0, 0, 0, 0, 0, 1, 2]
        for run_index in range(MIN_SESSIONS_FOR_FIT + 10):
            _, suggs = _Fixture.make_run_with_destinations(
                scope=scope,
                host=host,
                host_sentence=sentence,
                run_index=run_index,
                destinations=dests,
            )
            _Fixture.seed_session(
                suggestions=suggs,
                clicked_index=click_pattern[run_index % len(click_pattern)],
            )
        result = fit_and_persist_from_impressions()
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.observations, MIN_IMPRESSIONS_FOR_FIT)
        self.assertGreaterEqual(result.sessions, MIN_SESSIONS_FOR_FIT)
        # Top-ranked dest gets way more clicks than examinations-
        # without-click → relevance well above the 0.5 prior mean.
        top_dest_pk = dests[0].pk
        self.assertGreater(result.relevance[top_dest_pk], prior_mean())
        # Round-trip via the load API.
        self.assertAlmostEqual(
            relevance_for(top_dest_pk), result.relevance[top_dest_pk]
        )

    def test_no_click_session_treated_as_full_examination(self) -> None:
        """Sessions with clicked_index=None → all docs marked examined."""
        scope = _Fixture.make_scope()
        host, sentence = _Fixture.make_host_with_sentence(scope, 1300)
        dests = [
            _Fixture.make_content_item(scope=scope, content_id=5000 + i, title=f"d{i}")
            for i in range(10)
        ]
        # All sessions are no-click.
        for run_index in range(MIN_SESSIONS_FOR_FIT + 10):
            _, suggs = _Fixture.make_run_with_destinations(
                scope=scope,
                host=host,
                host_sentence=sentence,
                run_index=run_index,
                destinations=dests,
            )
            _Fixture.seed_session(suggestions=suggs, clicked_index=None)
        result = fit_and_persist_from_impressions()
        self.assertIsNotNone(result)
        # No clicks anywhere → every doc's relevance estimate should
        # be below the prior mean (heavy negative evidence).
        for dest in dests:
            self.assertLess(result.relevance[dest.pk], prior_mean())

    def test_idempotent_refit_overwrites_in_place(self) -> None:
        """Re-running on the same data updates AppSetting in place."""
        from apps.core.models import AppSetting

        scope = _Fixture.make_scope()
        host, sentence = _Fixture.make_host_with_sentence(scope, 1400)
        dests = [
            _Fixture.make_content_item(scope=scope, content_id=6000 + i, title=f"d{i}")
            for i in range(10)
        ]
        for run_index in range(MIN_SESSIONS_FOR_FIT + 10):
            _, suggs = _Fixture.make_run_with_destinations(
                scope=scope,
                host=host,
                host_sentence=sentence,
                run_index=run_index,
                destinations=dests,
            )
            _Fixture.seed_session(suggestions=suggs, clicked_index=run_index % 4)
        first = fit_and_persist_from_impressions()
        rows_first = AppSetting.objects.filter(
            key__startswith="cascade_click_em."
        ).count()
        second = fit_and_persist_from_impressions()
        rows_second = AppSetting.objects.filter(
            key__startswith="cascade_click_em."
        ).count()
        self.assertEqual(rows_first, rows_second)
        # Same data → same per-destination relevance.
        for dest_pk, rel in first.relevance.items():
            self.assertAlmostEqual(second.relevance[dest_pk], rel, places=6)
