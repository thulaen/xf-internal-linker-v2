from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auto_issues.models import AutoIssue
from apps.work_queue.models import AgentRepairAttempt, SelfHealingDecision
from apps.work_queue.services.agent_attempts import record_repair_attempt
from apps.work_queue.services.self_healing import record_self_healing_decision


@override_settings(ALLOWED_HOSTS=["testserver"])
class WorkQueueApiTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="operator")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_overview_shows_autoissue_without_page_specific_state(self):
        """Given an AutoIssue changes, When overview refreshes, Then it appears."""
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="work-queue-test",
            title="Celery queue timeout blocks imports",
            affected_files=["backend/apps/pipeline/tasks.py"],
            severity=AutoIssue.SEVERITY_HIGH,
            priority_score=1.0,
        )
        AutoIssue.objects.filter(pk=issue.pk).update(
            priority_score=999.0,
            last_seen=timezone.now() + timedelta(days=30),
        )

        response = self.client.get("/api/work-queue/overview/")

        self.assertEqual(response.status_code, 200)
        keys = [row["key"] for row in response.json()["now"]]
        self.assertIn(f"autoissue-{issue.id}", keys)

    def test_duplicate_file_claim_is_marked_conflicted(self):
        """Given two agents claim the same file, When second claims, Then conflict."""
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="claim-test",
            title="Shared file needs repair",
            affected_files=["backend/apps/core/views.py"],
        )
        key = f"autoissue-{issue.id}"
        first = self.client.post(f"/api/work-queue/tasks/{key}/claim/", {"agent": "codex"})
        second = self.client.post(f"/api/work-queue/tasks/{key}/claim/", {"agent": "claude"})

        self.assertEqual(first.json()["status"], "claimed")
        self.assertEqual(second.json()["status"], "conflicted")

    def test_attempt_loop_cap_blocks_fourth_same_failed_fix(self):
        """Given same failed fix repeats, When fourth is recorded, Then it blocks."""
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="attempt-test",
            title="Repeated failed repair",
        )
        key = f"autoissue-{issue.id}"
        for _ in range(3):
            record_repair_attempt(
                item_key=key,
                agent="codex",
                attempt_fingerprint="same-patch",
                result=AgentRepairAttempt.RESULT_FAILED,
            )

        result = record_repair_attempt(
            item_key=key,
            agent="codex",
            attempt_fingerprint="same-patch",
            result=AgentRepairAttempt.RESULT_FAILED,
        )

        self.assertTrue(result["blocked_by_loop_cap"])
        self.assertEqual(result["result"], AgentRepairAttempt.RESULT_BLOCKED)

    def test_self_healing_only_recommends_latest_agent_commit(self):
        """Given agent commit broke backend, When recorded, Then revert is recommended."""
        decision = record_self_healing_decision(
            latest_commit_sha="abc123",
            latest_commit_author="Codex Agent",
            backend_health="failed",
            frontend_health="healthy",
            dirty_worktree=False,
        )

        self.assertEqual(decision.status, SelfHealingDecision.STATUS_REVERT_RECOMMENDED)
        self.assertTrue(decision.agent_authored)
