"""Focused tests for work queue service helpers."""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.work_queue.services import correlation, gui_projection, items, remediation
from apps.auto_issues.models import AutoIssue
from apps.work_queue.models import AgentRepairAttempt, SourceConfidence


class WorkQueueItemServiceTests(TestCase):
    def test_parse_item_key_accepts_known_prefixes(self) -> None:
        ref = items.parse_item_key("autoissue-42")

        self.assertEqual(ref.kind, "autoissue")
        self.assertEqual(ref.id, 42)
        self.assertEqual(ref.key, "autoissue-42")

    def test_parse_item_key_rejects_unknown_shape(self) -> None:
        with self.assertRaises(ValidationError):
            items.parse_item_key("issue-abc")

    def test_load_item_returns_autoissue(self) -> None:
        issue = _autoissue("load-item", affected_files=[" backend/apps/foo.py ", ""])

        loaded = items.load_item(items.parse_item_key(f"autoissue-{issue.id}"))

        self.assertEqual(loaded, issue)
        self.assertEqual(items.affected_files_for(loaded), [" backend/apps/foo.py "])

    def test_load_item_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ObjectDoesNotExist):
            items.load_item(items.WorkItemRef(kind="unknown", id=1, key="unknown-1"))


class WorkQueueRemediationTests(TestCase):
    def test_suggestion_prefers_first_affected_file(self) -> None:
        issue = _autoissue("suggest-file", affected_files=["backend/apps/core/views.py"])

        text = remediation.suggestion_for_item(issue)

        self.assertIn("backend/apps/core/views.py", text)
        self.assertIn("prior fixes", text)

    def test_historical_fix_suggestions_returns_resolved_lessons(self) -> None:
        resolved = _autoissue(
            "historical-match",
            status=AutoIssue.STATUS_RESOLVED,
            lessons_learned="Trap: hidden coupling. Fix shape: add focused test.",
        )
        resolved.resolved_at = timezone.now()
        resolved.save(update_fields=["resolved_at"])

        rows = remediation.historical_fix_suggestions(query="historical", limit=3)

        self.assertEqual(rows[0]["id"], resolved.id)
        self.assertIn("Trap:", rows[0]["lessons_learned"])


class WorkQueueCorrelationTests(TestCase):
    def test_build_cause_groups_groups_by_canonical_fingerprint(self) -> None:
        first = _autoissue(
            "cause-a",
            source=AutoIssue.SOURCE_AGENT,
            priority_score=0.6,
            affected_files=["backend/apps/a.py"],
        )
        second = _autoissue(
            "cause-b",
            source=AutoIssue.SOURCE_MUTATION,
            priority_score=0.9,
            affected_files=["backend/apps/b.py"],
        )
        AutoIssue.objects.filter(pk__in=[first.pk, second.pk]).update(
            canonical_fingerprint="work-queue-shared-cause",
            priority_score=999.0,
            last_seen=timezone.now() + timedelta(days=30),
        )

        groups = correlation.build_cause_groups(limit=100)
        group = next(
            row
            for row in groups
            if {"backend/apps/a.py", "backend/apps/b.py"}.issubset(row["affected_files"])
        )

        self.assertEqual(group["source_count"], 2)
        self.assertEqual(group["max_priority"], 999.0)
        self.assertEqual(
            group["affected_files"],
            ["backend/apps/a.py", "backend/apps/b.py"],
        )

    def test_contradiction_count_ignores_resolved_issues(self) -> None:
        _autoissue("active contradiction")
        _autoissue("resolved contradiction", status=AutoIssue.STATUS_RESOLVED)

        self.assertEqual(correlation.contradiction_count(), 1)


class WorkQueueGuiProjectionTests(TestCase):
    def test_build_overview_combines_items_and_live_signals(self) -> None:
        issue = _autoissue("overview", priority_score=0.8)
        SourceConfidence.objects.create(source="agent", trust_score=0.7, reason="fresh")

        overview = gui_projection.build_overview(limit=50)

        keys = [row["key"] for row in overview["now"]]
        self.assertIn(f"autoissue-{issue.id}", keys)
        self.assertEqual(overview["live_signals"]["source_confidence"][0]["source"], "agent")
        self.assertIn("work_queue", overview["real_time_topics"])

    def test_build_feed_orders_recent_items(self) -> None:
        issue = _autoissue("feed", priority_score=0.5)
        feed = gui_projection.build_feed(limit=5)
        keys = {row["key"] for row in feed["items"]}

        self.assertIn(f"autoissue-{issue.id}", keys)

    def test_rehearse_item_loads_required_checks_and_attempt_summary(self) -> None:
        issue = _autoissue(
            "rehearse",
            affected_files=["backend/apps/work_queue/services/items.py"],
        )
        key = f"autoissue-{issue.id}"
        AgentRepairAttempt.objects.create(
            item_kind="autoissue",
            item_id=issue.id,
            item_key=key,
            agent="codex",
            attempt_fingerprint="abc",
            result=AgentRepairAttempt.RESULT_FAILED,
        )

        result = gui_projection.rehearse_item(key)

        self.assertEqual(result["item_key"], key)
        self.assertEqual(result["attempt_quality"]["failed_count"], 1)
        self.assertIn("Run the focused backend test through Docker", result["required_checks"])

    def test_required_checks_combines_frontend_and_backend(self) -> None:
        class DummyItem:
            affected_files = ["frontend/src/app.ts", "backend/apps/views.py"]
        
        checks = gui_projection._required_checks(DummyItem())
        self.assertIn("Run the Angular test or build for the touched page", checks)
        self.assertIn("Run the focused backend test through Docker", checks)

    def test_required_checks_identifies_autoissue_fix(self) -> None:
        class DummyItem:
            affected_files = ["apps/work_queue/services/autoissue.py"]
        
        checks = gui_projection._required_checks(DummyItem())
        self.assertIn("Run the AutoIssue specific tests for this bug class", checks)


def _autoissue(
    title: str,
    *,
    source: str = AutoIssue.SOURCE_AGENT,
    status: str = AutoIssue.STATUS_OPEN,
    canonical_fingerprint: str = "",
    priority_score: float = 0.5,
    affected_files: list[str] | None = None,
    lessons_learned: str = "",
) -> AutoIssue:
    issue = AutoIssue.objects.create(
        source=source,
        external_id=f"work-queue-{title}",
        title=title,
        status=status,
        canonical_fingerprint=canonical_fingerprint,
        priority_score=priority_score,
        affected_files=affected_files or [],
        lessons_learned=lessons_learned,
    )
    AutoIssue.objects.filter(pk=issue.pk).update(
        priority_score=999.0,
        last_seen=timezone.now() + timedelta(days=30),
    )
    issue.refresh_from_db()
    return issue
