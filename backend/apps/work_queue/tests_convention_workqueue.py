"""Convention tests for work_queue pure logic — SimpleTestCase, DB mocked.

These tightly assert string, numeric, comparison, and boolean logic so mutation
survivors are killed. They cover the two real bugs fixed in
``services/gui_projection.py``:

* ``ACTIVE_PAPER_STATUSES`` had the mutmut-style ``"XXin_progressXX"`` literal
  instead of ``"in_progress"`` (string typo).
* ``build_feed`` did ``_autoissue_items(limit) - _paper_items(limit)`` which
  raises ``TypeError`` because Python lists do not support subtraction; it must
  concatenate with ``+`` like ``build_overview`` does.
"""

from __future__ import annotations

from unittest import mock

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.test import SimpleTestCase

from apps.work_queue.services import (
    correlation,
    gui_projection,
    items,
    remediation,
    self_healing,
)
from apps.work_queue.models import SelfHealingDecision


class GuiProjectionBugFixTests(SimpleTestCase):
    """The two real bugs that were flagged and fixed."""

    def test_active_paper_statuses_uses_in_progress_literal(self) -> None:
        # break_old: "in_progress" present; break_new: would fail if "XXin_progressXX".
        self.assertIn("in_progress", gui_projection.ACTIVE_PAPER_STATUSES)
        self.assertNotIn("XXin_progressXX", gui_projection.ACTIVE_PAPER_STATUSES)

    def test_active_paper_statuses_exact_set(self) -> None:
        self.assertEqual(
            gui_projection.ACTIVE_PAPER_STATUSES,
            {"open", "picked", "in_progress", "blocked", "deferred"},
        )

    def test_build_feed_concatenates_both_sources_without_typeerror(self) -> None:
        auto_rows = [
            {"key": "autoissue-1", "updated_at": "2026-06-01T00:00:00"},
            {"key": "autoissue-2", "updated_at": "2026-06-03T00:00:00"},
        ]
        paper_rows = [{"key": "papertrail-9", "updated_at": "2026-06-02T00:00:00"}]
        with mock.patch.object(
            gui_projection, "_autoissue_items", return_value=list(auto_rows)
        ), mock.patch.object(
            gui_projection, "_paper_items", return_value=list(paper_rows)
        ):
            feed = gui_projection.build_feed(limit=30)

        keys = [row["key"] for row in feed["items"]]
        # All three rows survive concatenation (subtraction would lose them / raise).
        self.assertEqual(set(keys), {"autoissue-1", "autoissue-2", "papertrail-9"})
        # Newest-first ordering by updated_at string.
        self.assertEqual(keys[0], "autoissue-2")
        self.assertIn("as_of", feed)

    def test_build_feed_respects_limit_slice(self) -> None:
        auto_rows = [
            {"key": f"autoissue-{n}", "updated_at": f"2026-06-0{n}T00:00:00"}
            for n in range(1, 4)
        ]
        with mock.patch.object(
            gui_projection, "_autoissue_items", return_value=list(auto_rows)
        ), mock.patch.object(gui_projection, "_paper_items", return_value=[]):
            feed = gui_projection.build_feed(limit=2)

        self.assertEqual(len(feed["items"]), 2)


class ItemsParseTests(SimpleTestCase):
    def test_parse_item_key_autoissue(self) -> None:
        ref = items.parse_item_key("autoissue-42")
        self.assertEqual(ref.kind, "autoissue")
        self.assertEqual(ref.id, 42)
        self.assertEqual(ref.key, "autoissue-42")

    def test_parse_item_key_papertrail(self) -> None:
        ref = items.parse_item_key("papertrail-7")
        self.assertEqual(ref.kind, "papertrail")
        self.assertEqual(ref.id, 7)

    def test_parse_item_key_rejects_missing_dash(self) -> None:
        with self.assertRaises(ValidationError):
            items.parse_item_key("autoissue42")

    def test_parse_item_key_rejects_unknown_prefix(self) -> None:
        with self.assertRaises(ValidationError):
            items.parse_item_key("issue-1")

    def test_parse_item_key_rejects_non_numeric_id(self) -> None:
        with self.assertRaises(ValidationError):
            items.parse_item_key("autoissue-abc")

    def test_load_item_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ObjectDoesNotExist):
            items.load_item(items.WorkItemRef(kind="weird", id=1, key="weird-1"))

    def test_affected_files_for_strips_blank_entries(self) -> None:
        class Dummy:
            affected_files = [" backend/x.py ", "", "   ", "backend/y.py"]

        self.assertEqual(
            items.affected_files_for(Dummy()),
            [" backend/x.py ", "backend/y.py"],
        )

    def test_affected_files_for_handles_missing_attr(self) -> None:
        self.assertEqual(items.affected_files_for(object()), [])


class RemediationSuggestionTests(SimpleTestCase):
    def test_suggestion_prefers_first_affected_file(self) -> None:
        class Dummy:
            affected_files = ["backend/apps/core/views.py", "backend/other.py"]
            title = "x"

        text = remediation.suggestion_for_item(Dummy())
        self.assertIn("backend/apps/core/views.py", text)
        self.assertIn("prior fixes", text)

    def test_suggestion_falls_back_to_title(self) -> None:
        class Dummy:
            affected_files: list[str] = []
            title = "Celery timeout"

        text = remediation.suggestion_for_item(Dummy())
        self.assertIn("Search resolved lessons", text)
        self.assertIn("Celery timeout", text)

    def test_suggestion_final_fallback(self) -> None:
        class Dummy:
            affected_files: list[str] = []
            title = ""

        self.assertEqual(
            remediation.suggestion_for_item(Dummy()),
            "Start by writing the smallest behavior test that proves the issue.",
        )


class RequiredChecksTests(SimpleTestCase):
    def test_base_checks_always_present(self) -> None:
        class Dummy:
            affected_files: list[str] = []

        checks = gui_projection._required_checks(Dummy())
        self.assertEqual(checks[0], "Read the source-backed spec")
        self.assertEqual(checks[1], "Write or update the focused test first")

    def test_frontend_and_backend_checks_added(self) -> None:
        class Dummy:
            affected_files = ["frontend/src/a.ts", "backend/apps/b.py"]

        checks = gui_projection._required_checks(Dummy())
        self.assertIn("Run the Angular test or build for the touched page", checks)
        self.assertIn("Run the focused backend test through Docker", checks)

    def test_autoissue_fix_check_added(self) -> None:
        class Dummy:
            affected_files = ["apps/work_queue/services/autoissue_x.py"]

        checks = gui_projection._required_checks(Dummy())
        self.assertIn("Run the AutoIssue specific tests for this bug class", checks)

    def test_non_autoissue_backend_path_excludes_autoissue_check(self) -> None:
        class Dummy:
            affected_files = ["backend/apps/pipeline/tasks.py"]

        checks = gui_projection._required_checks(Dummy())
        self.assertNotIn("Run the AutoIssue specific tests for this bug class", checks)


class BusinessImpactTests(SimpleTestCase):
    def test_queue_related_title_returns_delay_impact(self) -> None:
        class Dummy:
            title = "Celery worker stalled"

        self.assertIn("Background work may be delayed", gui_projection._business_impact(Dummy()))

    def test_redis_title_returns_delay_impact(self) -> None:
        class Dummy:
            title = "Redis connection lost"

        self.assertIn("Background work may be delayed", gui_projection._business_impact(Dummy()))

    def test_unrelated_title_returns_default(self) -> None:
        class Dummy:
            title = "Typo in heading"

        self.assertEqual(
            gui_projection._business_impact(Dummy()),
            "No business impact has been calculated yet.",
        )


class SelfHealingDecisionLogicTests(SimpleTestCase):
    def test_is_agent_author_detects_known_hints(self) -> None:
        self.assertTrue(self_healing._is_agent_author("Codex Agent"))
        self.assertTrue(self_healing._is_agent_author("claude-bot"))
        self.assertFalse(self_healing._is_agent_author("Jane Human"))

    def test_decide_not_broken_is_watching(self) -> None:
        status, reason = self_healing._decide(True, "healthy", "healthy", False)
        self.assertEqual(status, SelfHealingDecision.STATUS_WATCHING)
        self.assertEqual(reason, "Backend and frontend checks are not failing.")

    def test_decide_dirty_worktree_requires_manual_review(self) -> None:
        status, _ = self_healing._decide(True, "failed", "healthy", True)
        self.assertEqual(status, SelfHealingDecision.STATUS_MANUAL_REVIEW)

    def test_decide_non_agent_commit_is_blocked(self) -> None:
        status, _ = self_healing._decide(False, "failed", "healthy", False)
        self.assertEqual(status, SelfHealingDecision.STATUS_BLOCKED)

    def test_decide_agent_break_recommends_revert(self) -> None:
        status, _ = self_healing._decide(True, "failed", "healthy", False)
        self.assertEqual(status, SelfHealingDecision.STATUS_REVERT_RECOMMENDED)

    def test_decide_frontend_failure_also_counts_as_broken(self) -> None:
        status, _ = self_healing._decide(True, "healthy", "failed", False)
        self.assertEqual(status, SelfHealingDecision.STATUS_REVERT_RECOMMENDED)

    def test_allowed_action_for_revert_recommended(self) -> None:
        decision = SelfHealingDecision(status=SelfHealingDecision.STATUS_REVERT_RECOMMENDED)
        self.assertEqual(self_healing._allowed_action(decision), "manual_approve_revert")

    def test_allowed_action_default_is_watch(self) -> None:
        decision = SelfHealingDecision(status=SelfHealingDecision.STATUS_WATCHING)
        self.assertEqual(self_healing._allowed_action(decision), "watch")


class RefreshProjectionConstraintTests(SimpleTestCase):
    """The ``refresh_projection`` Celery task declares its helper-routing
    profile via ``@HelperConstraint``.

    Importing ``apps.work_queue.tasks`` applies the decorator (the changed
    lines), and ``get_constraint`` reads back the exact metadata the router
    consumes. No DB is touched: the decorator only annotates the callable.
    """

    def test_refresh_projection_carries_helper_constraint(self) -> None:
        from apps.core.helpers import get_constraint
        from apps.work_queue.tasks import refresh_projection

        wrapped = getattr(refresh_projection, "__wrapped__", refresh_projection)
        meta = get_constraint(wrapped)

        self.assertIsNotNone(
            meta,
            msg="refresh_projection must declare a @HelperConstraint so the "
            "routing engine knows it writes to the main Postgres node.",
        )
        # Exact values pin the changed decorator lines: a light Postgres-writing
        # projection refresh, ~256 MB RAM, ~5 s expected runtime.
        self.assertFalse(meta.cpu_intensive)
        self.assertFalse(meta.gpu_required)
        self.assertEqual(meta.storage_writes_to, "postgres_main")
        self.assertEqual(meta.ram_peak_mb, 256)
        self.assertEqual(meta.expected_seconds_p50, 5)


class CorrelationGroupPayloadTests(SimpleTestCase):
    def test_group_payload_counts_sources_and_max_priority(self) -> None:
        class Issue:
            def __init__(self, source, files, priority, title):
                self.source = source
                self.affected_files = files
                self.priority_score = priority
                self.title = title

        issues = [
            Issue("agent", ["backend/a.py"], 0.6, "shared cause"),
            Issue("mutation", ["backend/b.py"], 0.9, "shared cause"),
            Issue("agent", ["backend/a.py"], 0.4, "shared cause"),
        ]
        payload = correlation._group_payload("fp-1", issues)

        self.assertEqual(payload["fingerprint"], "fp-1")
        self.assertEqual(payload["title"], "shared cause")
        self.assertEqual(payload["source_count"], 2)
        self.assertEqual(payload["issue_count"], 3)
        self.assertEqual(payload["affected_files"], ["backend/a.py", "backend/b.py"])
        self.assertEqual(payload["max_priority"], 0.9)
        self.assertEqual(
            payload["next_action"],
            "Fix the shared cause once, then resolve every linked symptom.",
        )
