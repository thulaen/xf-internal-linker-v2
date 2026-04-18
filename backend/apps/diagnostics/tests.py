from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.diagnostics import health


class HealthCheckTests(TestCase):
    def test_check_native_scoring_reports_runtime_metadata(self):
        state, explanation, next_step, metadata = health.check_native_scoring()

        self.assertIn(state, {"healthy", "degraded", "failed"})
        self.assertTrue(explanation)
        self.assertTrue(next_step)
        self.assertIn("runtime_path", metadata)
        self.assertIn("fallback_active", metadata)
        self.assertIn("safe_to_use", metadata)
        self.assertIn("module_statuses", metadata)
        self.assertGreater(len(metadata["module_statuses"]), 0)
        self.assertIn("compiled_module_count", metadata)
        self.assertIn("benchmark_status", metadata)


@override_settings(SCHEDULER_CONTROL_TOKEN="scheduler-secret")
class SchedulerDispatchViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch(
        "apps.pipeline.tasks.dispatch_import_content",
        return_value={"job_id": "abc", "runtime_owner": "celery", "message": "queued"},
    )
    def test_scheduler_dispatch_accepts_import_job_with_token(
        self, dispatch_import_content
    ):
        response = self.client.post(
            "/api/system/status/internal/scheduler/dispatch/",
            {
                "task": "pipeline.import_content",
                "kwargs": {"source": "api", "mode": "full"},
                "periodic_task_name": "nightly-xenforo-sync",
            },
            format="json",
            HTTP_X_SCHEDULER_TOKEN="scheduler-secret",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["periodic_task_name"], "nightly-xenforo-sync")
        dispatch_import_content.assert_called_once_with(
            scope_ids=None,
            mode="full",
            source="api",
            file_path=None,
            job_id=None,
            force_reembed=False,
        )

    def test_scheduler_dispatch_rejects_bad_token(self):
        response = self.client.post(
            "/api/system/status/internal/scheduler/dispatch/",
            {
                "task": "pipeline.import_content",
                "kwargs": {"source": "api", "mode": "full"},
            },
            format="json",
            HTTP_X_SCHEDULER_TOKEN="wrong-token",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("did not match", response.json()["detail"])


class SignalContractTests(SimpleTestCase):
    """CI guard for the governance contract on every shipped signal.

    Every active entry in :mod:`apps.diagnostics.signal_registry` must
    fill the fields the Business Logic Checklist (§1, §3, §6) requires.
    This test asserts ``validate_signal_contract()`` returns no
    violations. Any new signal added without governance metadata will
    fail this test at merge time.

    Uses :class:`SimpleTestCase` because the registry is pure Python
    with no DB access.
    """

    def test_every_active_signal_has_complete_governance_contract(self):
        from apps.diagnostics.signal_registry import validate_signal_contract

        violations = validate_signal_contract()
        self.assertEqual(
            violations,
            [],
            msg=(
                "Signal contract violations found. Fix each active signal "
                "entry in apps/diagnostics/signal_registry.py so it has "
                "academic_source, source_kind, neutral_value, and at "
                "least one diagnostic_surface. Violations:\n- "
                + "\n- ".join(violations)
            ),
        )

    def test_registry_has_no_duplicate_ids(self):
        from apps.diagnostics.signal_registry import SIGNALS

        ids = [s.id for s in SIGNALS]
        self.assertEqual(
            len(ids),
            len(set(ids)),
            "Duplicate signal ids found in SIGNALS list.",
        )

    def test_get_signal_returns_definition_for_known_id(self):
        from apps.diagnostics.signal_registry import get_signal

        semantic = get_signal("semantic_similarity")
        self.assertIsNotNone(semantic)
        self.assertEqual(semantic.type, "ranking")
        self.assertEqual(semantic.architecture_lane, "cpp_first")

    def test_get_signal_returns_none_for_unknown_id(self):
        from apps.diagnostics.signal_registry import get_signal

        self.assertIsNone(get_signal("does_not_exist"))

    def test_signals_by_status_filters_correctly(self):
        from apps.diagnostics.signal_registry import SIGNALS, signals_by_status

        active = signals_by_status("active")
        self.assertGreater(len(active), 0)
        for sig in active:
            self.assertEqual(sig.status, "active")

        # Total count sanity: every signal in SIGNALS has some status.
        status_sum = (
            len(signals_by_status("active"))
            + len(signals_by_status("pending"))
            + len(signals_by_status("deprecated"))
        )
        self.assertEqual(status_sum, len(SIGNALS))


class NegativeMemoryDiagnosticsViewTests(TestCase):
    """Phase 1v — GET /api/diagnostics/suppressed-pairs/ surfaces RejectedPair
    counters for the Diagnostics page.
    """

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        self.client = APIClient()
        user = get_user_model().objects.create_user(
            username="diag-user", password="pass"
        )
        self.client.force_authenticate(user=user)

    def test_empty_table_returns_zero_counts(self) -> None:
        response = self.client.get("/api/system/status/suppressed-pairs/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_suppressed_pairs"], 0)
        self.assertEqual(payload["total_rejected_pairs"], 0)
        self.assertEqual(payload["total_rejections_lifetime"], 0)
        self.assertIsNone(payload["most_recent_rejection_at"])
        self.assertGreater(payload["active_suppression_window_days"], 0)

    def test_counts_active_pairs_lifetime_rejections_and_most_recent(self) -> None:
        from datetime import timedelta

        from apps.content.models import ContentItem
        from apps.suggestions.models import (
            REJECTED_PAIR_SUPPRESSION_DAYS,
            RejectedPair,
        )
        from django.utils import timezone

        host = ContentItem.objects.create(
            content_id=4001, content_type="thread", title="H"
        )
        dest_active = ContentItem.objects.create(
            content_id=4002, content_type="thread", title="DA"
        )
        dest_stale = ContentItem.objects.create(
            content_id=4003, content_type="thread", title="DS"
        )

        # Active pair: rejected 3 times, latest just now.
        RejectedPair.record_rejection(host_id=host.pk, destination_id=dest_active.pk)
        RejectedPair.record_rejection(host_id=host.pk, destination_id=dest_active.pk)
        RejectedPair.record_rejection(host_id=host.pk, destination_id=dest_active.pk)

        # Stale pair: rejected once but past the suppression window.
        RejectedPair.record_rejection(host_id=host.pk, destination_id=dest_stale.pk)
        stale_ts = timezone.now() - timedelta(days=REJECTED_PAIR_SUPPRESSION_DAYS + 5)
        RejectedPair.objects.filter(destination_id=dest_stale.pk).update(
            last_rejected_at=stale_ts
        )

        response = self.client.get("/api/system/status/suppressed-pairs/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_suppressed_pairs"], 1)
        self.assertEqual(payload["total_rejected_pairs"], 2)
        # 3 rejections on the active pair + 1 on the stale pair.
        self.assertEqual(payload["total_rejections_lifetime"], 4)
        self.assertIsNotNone(payload["most_recent_rejection_at"])
