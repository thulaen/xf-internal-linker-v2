"""Tests for the daily data-retention sweep.

Covers the three new prune blocks added on 2026-04-25 (B.5
SuggestionImpression, B.6 SuggestionPresentation, B.7 pending /
stale Suggestion) plus the @scheduled_job wrapper that the runner
fires at 22:30 inside the operator window.

The original 7 prune blocks (SearchMetric, PipelineRun,
ContentMetricSnapshot, superseded Suggestion, AuditEntry, ErrorLog,
WebhookReceipt) have been functionally stable for months and are
not retested here — these tests only cover the new 2026-04-25
additions plus the wrapper integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_tz

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from apps.pipeline.tasks import (
    RETENTION_PREVIEW_KEY_IMPRESSIONS,
    RETENTION_PREVIEW_KEY_LAST_RUN_AT,
    nightly_data_retention,
)


class _RetentionFixtureMixin:
    """Helpers that build the minimum object graph each test needs.

    We avoid relying on a single shared fixture so each test can
    seed exactly the rows it cares about — the prune logic is
    cutoff-sensitive and fragile to off-by-one errors.
    """

    def _make_suggestion(self, status: str = "pending"):
        """Build a (ContentItem, Post, Sentence, Suggestion) tuple suitable
        for retention tests. Creates fresh rows with unique
        content_ids on each call so callers can stack multiple
        suggestions in one test. Uses ``get_or_create`` for the scope
        so calls within one test reuse the scope without conflicting
        with other tests' rolled-back transactions.
        """
        from apps.content.models import ContentItem, Post, Sentence, ScopeItem
        from apps.suggestions.models import PipelineRun, Suggestion

        scope, _ = ScopeItem.objects.get_or_create(
            scope_id=99,
            defaults={"scope_type": "node", "title": "retention-test"},
        )

        # Cheap unique counter per test method — a free function attr
        # is reset by Django's transaction rollback only if we tied
        # it to a model. Easier: derive from a count of existing
        # rows.
        idx = ContentItem.objects.filter(
            content_id__gte=70_000, content_id__lt=90_000
        ).count() + 1

        host = ContentItem.objects.create(
            content_id=70_000 + idx,
            content_type="thread",
            title=f"Host {idx}",
            scope=scope,
        )
        host_post = Post.objects.create(
            content_item=host, raw_bbcode="x", clean_text="x"
        )
        sent = Sentence.objects.create(
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
            content_id=80_000 + idx,
            content_type="thread",
            title=f"Dest {idx}",
            scope=scope,
        )
        run = PipelineRun.objects.create()
        return Suggestion.objects.create(
            pipeline_run=run,
            destination=dest,
            host=host,
            host_sentence=sent,
            destination_title=f"Dest {idx}",
            host_sentence_text="A host sentence.",
            anchor_phrase="anchor",
            anchor_start=0,
            anchor_end=6,
            anchor_confidence="strong",
            score_final=0.5,
            status=status,
        )


class SuggestionImpressionPruneTests(_RetentionFixtureMixin, TestCase):
    """B.5 — 90-day prune of SuggestionImpression rows."""

    def test_old_rows_get_deleted_recent_rows_kept(self) -> None:
        from apps.suggestions.models import SuggestionImpression

        now = timezone.now()
        sug = self._make_suggestion()

        old = SuggestionImpression.objects.create(
            suggestion=sug, position=0, clicked=False
        )
        recent = SuggestionImpression.objects.create(
            suggestion=sug, position=1, clicked=True
        )
        # Force the "old" row's auto_now_add timestamp into the past.
        SuggestionImpression.objects.filter(pk=old.pk).update(
            impressed_at=now - timedelta(days=120)
        )

        results = nightly_data_retention()

        self.assertEqual(results["suggestion_impressions_deleted"], 1)
        self.assertFalse(
            SuggestionImpression.objects.filter(pk=old.pk).exists()
        )
        self.assertTrue(
            SuggestionImpression.objects.filter(pk=recent.pk).exists()
        )

    def test_persists_cardinality_preview_to_appsetting(self) -> None:
        from apps.core.models import AppSetting
        from apps.suggestions.models import SuggestionImpression

        sug = self._make_suggestion()
        for _ in range(3):
            row = SuggestionImpression.objects.create(
                suggestion=sug, position=0, clicked=False
            )
            SuggestionImpression.objects.filter(pk=row.pk).update(
                impressed_at=timezone.now() - timedelta(days=200)
            )

        nightly_data_retention()

        post = AppSetting.objects.get(key=RETENTION_PREVIEW_KEY_IMPRESSIONS)
        self.assertEqual(int(post.value), 0)  # post-prune ⇒ none aged-out
        last = AppSetting.objects.get(
            key=f"{RETENTION_PREVIEW_KEY_IMPRESSIONS}.last_count"
        )
        self.assertEqual(int(last.value), 3)


class SuggestionPresentationPruneTests(_RetentionFixtureMixin, TestCase):
    """B.6 — 180-day prune of SuggestionPresentation rows."""

    def test_old_rows_get_deleted_recent_rows_kept(self) -> None:
        from apps.suggestions.models import SuggestionPresentation

        sug = self._make_suggestion()
        user = User.objects.create_user(username="testuser", password="x")

        today = timezone.now().date()
        old = SuggestionPresentation.objects.create(
            suggestion=sug,
            user=user,
            presented_date=today - timedelta(days=200),
        )
        recent = SuggestionPresentation.objects.create(
            suggestion=sug,
            user=user,
            presented_date=today - timedelta(days=30),
        )

        results = nightly_data_retention()

        self.assertEqual(results["suggestion_presentations_deleted"], 1)
        self.assertFalse(
            SuggestionPresentation.objects.filter(pk=old.pk).exists()
        )
        self.assertTrue(
            SuggestionPresentation.objects.filter(pk=recent.pk).exists()
        )


class PendingStaleSuggestionPruneTests(_RetentionFixtureMixin, TestCase):
    """B.7 — 365-day prune of pending / stale Suggestion rows."""

    def test_old_pending_gets_deleted(self) -> None:
        from apps.suggestions.models import Suggestion

        old = self._make_suggestion(status="pending")
        cutoff = timezone.now() - timedelta(days=400)
        Suggestion.objects.filter(pk=old.pk).update(updated_at=cutoff)
        # Sanity: confirm the .update() really did persist a 400-day-old
        # timestamp (auto_now=True is bypassed by .update(), per the
        # Django docs, but verify rather than trust).
        old.refresh_from_db()
        self.assertLess(
            old.updated_at,
            timezone.now() - timedelta(days=399),
            f"updated_at did not persist: got {old.updated_at!r}",
        )

        results = nightly_data_retention()

        self.assertEqual(results["non_approved_suggestions_deleted"], 1)
        self.assertFalse(Suggestion.objects.filter(pk=old.pk).exists())

    def test_old_stale_gets_deleted(self) -> None:
        from apps.suggestions.models import Suggestion

        old = self._make_suggestion(status="stale")
        Suggestion.objects.filter(pk=old.pk).update(
            updated_at=timezone.now() - timedelta(days=400)
        )

        nightly_data_retention()

        self.assertFalse(Suggestion.objects.filter(pk=old.pk).exists())

    def test_old_approved_is_kept_indefinitely(self) -> None:
        """Approved Suggestions are the operator's audit trail and
        must NEVER be deleted — even at 5+ years old."""
        from apps.suggestions.models import Suggestion

        ancient = self._make_suggestion(status="approved")
        Suggestion.objects.filter(pk=ancient.pk).update(
            updated_at=timezone.now() - timedelta(days=2000)
        )

        nightly_data_retention()

        self.assertTrue(Suggestion.objects.filter(pk=ancient.pk).exists())

    def test_recent_pending_kept(self) -> None:
        from apps.suggestions.models import Suggestion

        recent = self._make_suggestion(status="pending")
        # Default updated_at is roughly now → safely inside the year.
        nightly_data_retention()
        self.assertTrue(Suggestion.objects.filter(pk=recent.pk).exists())


class RetentionTimestampTests(_RetentionFixtureMixin, TestCase):
    def test_timestamp_persisted_after_run(self) -> None:
        from apps.core.models import AppSetting

        nightly_data_retention()

        row = AppSetting.objects.get(key=RETENTION_PREVIEW_KEY_LAST_RUN_AT)
        # Timestamp parses cleanly as ISO-8601.
        parsed = datetime.fromisoformat(row.value)
        self.assertIsNotNone(parsed.tzinfo)


class ProgressCallbackTests(_RetentionFixtureMixin, TestCase):
    def test_progress_callback_called_with_increasing_pcts(self) -> None:
        calls: list[tuple[float, str]] = []

        def cb(pct: float, msg: str) -> None:
            calls.append((pct, msg))

        nightly_data_retention(progress_callback=cb)

        self.assertGreaterEqual(len(calls), 5)
        pcts = [c[0] for c in calls]
        # First call is 0.0; last is 100.0; calls are non-decreasing.
        self.assertEqual(pcts[0], 0.0)
        self.assertEqual(pcts[-1], 100.0)
        for prev, curr in zip(pcts, pcts[1:]):
            self.assertLessEqual(prev, curr)

    def test_progress_callback_default_is_noop(self) -> None:
        # Without a callback the function still completes normally.
        results = nightly_data_retention()
        self.assertIn("suggestion_impressions_deleted", results)

    def test_progress_callback_exception_does_not_crash_run(self) -> None:
        def cb(pct: float, msg: str) -> None:
            raise RuntimeError("simulated dashboard outage")

        # Must not propagate — the dashboard should never be able to
        # break the prune sweep.
        results = nightly_data_retention(progress_callback=cb)
        self.assertIn("suggestion_impressions_deleted", results)


class ScheduledJobWrapperTests(_RetentionFixtureMixin, TestCase):
    """The @scheduled_job entry in apps.scheduled_updates.jobs that
    delegates to nightly_data_retention with checkpoint bridging."""

    def test_wrapper_runs_retention_and_emits_checkpoints(self) -> None:
        from apps.scheduled_updates.jobs import run_daily_data_retention
        from apps.suggestions.models import SuggestionImpression

        # Seed an aged-out impression so the inner function does work.
        sug = self._make_suggestion()
        old = SuggestionImpression.objects.create(
            suggestion=sug, position=0, clicked=False
        )
        SuggestionImpression.objects.filter(pk=old.pk).update(
            impressed_at=timezone.now() - timedelta(days=120)
        )

        progress: list[tuple[float, str]] = []

        def fake_checkpoint(*, progress_pct: float, message: str = "") -> None:
            progress.append((progress_pct, message))

        run_daily_data_retention(job=None, checkpoint=fake_checkpoint)

        # Inner function ran (impression deleted).
        self.assertFalse(
            SuggestionImpression.objects.filter(pk=old.pk).exists()
        )
        # Checkpoint bridge fired at least once.
        self.assertGreaterEqual(len(progress), 1)
        self.assertEqual(progress[-1][0], 100.0)


class CeleryBeatScheduleTests(TestCase):
    def test_no_pipeline_nightly_data_retention_beat_entry(self) -> None:
        """The @scheduled_job path is the canonical caller now —
        leaving the celery beat entry in place would double-fire
        the prune."""
        from django.conf import settings

        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertNotEqual(
                entry.get("task"),
                "pipeline.nightly_data_retention",
                f"Beat schedule entry {name!r} still targets the "
                "retention task. It should be removed in favour of "
                "the @scheduled_job entry in apps.scheduled_updates.jobs.",
            )


# Mark unused import as documented (silence ruff F401 on imports kept
# for future test extensions).
_ = dt_tz
