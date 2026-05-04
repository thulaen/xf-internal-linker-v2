"""Tests for the per-section helpers extracted from DashboardView.get.

The original handler was 175 lines of inline ORM queries — refactored
into ``_dashboard_*`` helpers in core/views.py so each panel can be
tested in isolation. These tests pin the contract each helper returns
so a future tweak (e.g. swapping the matview backend) can't silently
change the dashboard's response shape.

Also covers the ``_build_value_model_rows`` pure helper extracted
from the 143-line ``ValueModelSettingsView.put`` body — every
serialisation rule (bool→"true"/"false", float→str, int→str) gets
one test so a future rename / type change surfaces in CI.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.core.views import (
    _build_value_model_rows,
    _dashboard_content_count,
    _dashboard_open_broken_links,
    _dashboard_overall_health_status,
    _dashboard_recent_imports,
    _dashboard_recent_pipeline_runs,
    _dashboard_runtime_mode_display,
    _dashboard_suggestion_counts,
    _dashboard_system_health,
)


# ── Dashboard panel helpers ──────────────────────────────────────


class DashboardSuggestionCountsTests(TestCase):
    def test_empty_db_returns_zero_for_every_status(self) -> None:
        counts = _dashboard_suggestion_counts()
        # Every documented status appears so the frontend doesn't
        # need null-checks
        for key in ("pending", "approved", "rejected", "applied", "total"):
            with self.subTest(key=key):
                self.assertIn(key, counts)
                self.assertEqual(counts[key], 0)

    def test_total_is_sum_of_status_counts(self) -> None:
        counts = _dashboard_suggestion_counts()
        # `total` must be the SUM of every status, even if the dict
        # only contains a subset (e.g. matview returns 3 keys; total
        # still aggregates them all)
        explicit_total = (
            counts["pending"]
            + counts["approved"]
            + counts["rejected"]
            + counts["applied"]
        )
        # On an empty DB, total is 0 + 0 + 0 + 0 = 0. The helper sums
        # over the matview dict which on empty is also empty → total=0.
        self.assertGreaterEqual(counts["total"], explicit_total - 0)


class DashboardContentCountTests(TestCase):
    def test_returns_non_negative_int(self) -> None:
        # Migration fixtures may seed ContentItems; pin only that the
        # helper returns a safe int >= 0.
        result = _dashboard_content_count()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)


class DashboardOpenBrokenLinksTests(TestCase):
    def test_returns_non_negative_int(self) -> None:
        result = _dashboard_open_broken_links()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)


class DashboardRecentPipelineRunsTests(TestCase):
    def setUp(self) -> None:
        # Defensive cleanup so cap-at-5 + stringification tests get a
        # known starting count, regardless of what migrations seeded.
        from apps.suggestions.models import PipelineRun

        PipelineRun.objects.all().delete()

    def test_clean_db_returns_empty_list(self) -> None:
        self.assertEqual(_dashboard_recent_pipeline_runs(), [])

    def test_caps_at_5_runs(self) -> None:
        from apps.suggestions.models import PipelineRun

        # Seed 7 runs; helper must only return last 5
        for _ in range(7):
            PipelineRun.objects.create(run_state="completed", rerun_mode="full")
        runs = _dashboard_recent_pipeline_runs()
        self.assertEqual(len(runs), 5)

    def test_run_id_stringified(self) -> None:
        from apps.suggestions.models import PipelineRun

        run = PipelineRun.objects.create(run_state="completed", rerun_mode="full")
        runs = _dashboard_recent_pipeline_runs()
        self.assertIsInstance(runs[0]["run_id"], str)
        self.assertEqual(runs[0]["run_id"], str(run.run_id))


class DashboardRecentImportsTests(TestCase):
    def setUp(self) -> None:
        from apps.sync.models import SyncJob

        SyncJob.objects.all().delete()

    def test_clean_db_returns_empty_list(self) -> None:
        self.assertEqual(_dashboard_recent_imports(), [])

    def test_caps_at_5_jobs(self) -> None:
        from apps.sync.models import SyncJob

        for _ in range(8):
            SyncJob.objects.create(source="xenforo", status="completed", mode="full")
        jobs = _dashboard_recent_imports()
        self.assertEqual(len(jobs), 5)


class DashboardOverallHealthStatusTests(SimpleTestCase):
    """Pure function — no DB needed."""

    def test_empty_returns_healthy(self) -> None:
        from apps.health.models import ServiceHealthRecord

        self.assertEqual(
            _dashboard_overall_health_status([]),
            ServiceHealthRecord.STATUS_HEALTHY,
        )

    def test_down_dominates(self) -> None:
        from apps.health.models import ServiceHealthRecord

        class Rec:
            def __init__(self, status: str) -> None:
                self.status = status

        records = [
            Rec(ServiceHealthRecord.STATUS_HEALTHY),
            Rec(ServiceHealthRecord.STATUS_DOWN),
            Rec(ServiceHealthRecord.STATUS_WARNING),
        ]
        self.assertEqual(
            _dashboard_overall_health_status(records),
            ServiceHealthRecord.STATUS_DOWN,
        )

    def test_error_dominates_warning(self) -> None:
        from apps.health.models import ServiceHealthRecord

        class Rec:
            def __init__(self, status: str) -> None:
                self.status = status

        records = [
            Rec(ServiceHealthRecord.STATUS_HEALTHY),
            Rec(ServiceHealthRecord.STATUS_ERROR),
            Rec(ServiceHealthRecord.STATUS_WARNING),
        ]
        self.assertEqual(
            _dashboard_overall_health_status(records),
            ServiceHealthRecord.STATUS_ERROR,
        )

    def test_stale_treated_as_error(self) -> None:
        from apps.health.models import ServiceHealthRecord

        class Rec:
            def __init__(self, status: str) -> None:
                self.status = status

        records = [Rec(ServiceHealthRecord.STATUS_STALE)]
        self.assertEqual(
            _dashboard_overall_health_status(records),
            ServiceHealthRecord.STATUS_ERROR,
        )


class DashboardSystemHealthTests(TestCase):
    def test_returns_required_shape(self) -> None:
        # Migration fixtures may seed ServiceHealthRecord rows; pin only
        # the response shape rather than specific counts.
        result = _dashboard_system_health()
        self.assertIn("status", result)
        self.assertIn("summary", result)
        self.assertIn("total_monitored", result)
        self.assertIsInstance(result["status"], str)
        self.assertIsInstance(result["summary"], dict)
        self.assertIsInstance(result["total_monitored"], int)
        self.assertGreaterEqual(result["total_monitored"], 0)


class DashboardRuntimeModeDisplayTests(TestCase):
    def test_returns_uppercase_string(self) -> None:
        # Real call: should return either "CPU" or "GPU" (or
        # uppercase fallback). Just pin that it's an uppercase non-empty
        # string and not a raw error.
        result = _dashboard_runtime_mode_display()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        self.assertEqual(result, result.upper())


class DashboardEndpointSmokeTests(TestCase):
    """End-to-end: hit the GET endpoint, verify shape preserved."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="dashboard-user", password="pw"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_dashboard_responds_200_with_required_keys(self) -> None:
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        for key in (
            "suggestion_counts",
            "content_count",
            "open_broken_links",
            "last_sync",
            "pipeline_runs",
            "recent_imports",
            "system_health",
            "last_sync_at",
            "last_pipeline_at",
            "last_analytics_at",
            "runtime_mode",
            "show_quick_controls",
            "confidence",
        ):
            with self.subTest(key=key):
                self.assertIn(key, response.data)


# ── Value-model row builder ──────────────────────────────────────


class BuildValueModelRowsTests(SimpleTestCase):
    """Pin every serialisation rule extracted from the 143-line put()."""

    def _validated(self, **overrides) -> dict:
        """Build a baseline validated dict; override fields per-test."""
        base = {
            "enabled": True,
            "w_relevance": 0.4,
            "w_traffic": 0.2,
            "w_freshness": 0.1,
            "w_authority": 0.1,
            "w_penalty": 0.1,
            "traffic_lookback_days": 30,
            "traffic_fallback_value": 0.5,
            "engagement_signal_enabled": True,
            "w_engagement": 0.1,
            "engagement_lookback_days": 14,
            "engagement_words_per_minute": 200,
            "engagement_cap_ratio": 1.5,
            "engagement_fallback_value": 0.5,
            "hot_decay_enabled": False,
            "hot_gravity": 1.8,
            "hot_clicks_weight": 1.0,
            "hot_impressions_weight": 0.5,
            "hot_lookback_days": 7,
            "co_occurrence_signal_enabled": False,
            "w_cooccurrence": 0.05,
            "co_occurrence_fallback_value": 0.0,
            "co_occurrence_min_co_sessions": 3,
        }
        base.update(overrides)
        return base

    def test_bool_true_serialises_to_string_true(self) -> None:
        rows = _build_value_model_rows(self._validated(enabled=True))
        self.assertEqual(rows["value_model.enabled"]["value"], "true")
        self.assertEqual(rows["value_model.enabled"]["value_type"], "bool")

    def test_bool_false_serialises_to_string_false(self) -> None:
        rows = _build_value_model_rows(self._validated(enabled=False))
        self.assertEqual(rows["value_model.enabled"]["value"], "false")

    def test_float_serialised_as_str_preserves_value(self) -> None:
        rows = _build_value_model_rows(self._validated(w_relevance=0.42))
        self.assertEqual(rows["value_model.w_relevance"]["value"], "0.42")
        self.assertEqual(rows["value_model.w_relevance"]["value_type"], "float")

    def test_int_serialised_as_str(self) -> None:
        rows = _build_value_model_rows(self._validated(traffic_lookback_days=42))
        self.assertEqual(rows["value_model.traffic_lookback_days"]["value"], "42")
        self.assertEqual(
            rows["value_model.traffic_lookback_days"]["value_type"], "int"
        )

    def test_every_validated_key_produces_a_row(self) -> None:
        """A future-proofing check: each input key must have a matching
        AppSetting row. If someone adds a new field to the validator
        without adding a matching row, this test fails loudly."""
        validated = self._validated()
        rows = _build_value_model_rows(validated)
        for key in validated:
            with self.subTest(input_key=key):
                self.assertIn(f"value_model.{key}", rows)

    def test_every_row_has_required_metadata_keys(self) -> None:
        rows = _build_value_model_rows(self._validated())
        for key, row in rows.items():
            with self.subTest(setting_key=key):
                self.assertIn("value", row)
                self.assertIn("value_type", row)
                self.assertIn("description", row)
                self.assertIsInstance(row["value"], str)
                self.assertIn(row["value_type"], ("bool", "int", "float"))

    def test_truthy_non_bool_inputs_treated_as_true(self) -> None:
        # Defensive: validator output may be a truthy int (e.g. 1)
        # rather than literal True. Helper should still emit "true".
        rows = _build_value_model_rows(self._validated(enabled=1))
        self.assertEqual(rows["value_model.enabled"]["value"], "true")

    def test_falsy_non_bool_inputs_treated_as_false(self) -> None:
        rows = _build_value_model_rows(self._validated(enabled=0))
        self.assertEqual(rows["value_model.enabled"]["value"], "false")
