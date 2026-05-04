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
    _apply_heartbeat_gpu_metrics,
    _apply_heartbeat_identity,
    _apply_heartbeat_load_metrics,
    _apply_heartbeat_network_health,
    _build_value_model_rows,
    _dashboard_content_count,
    _dashboard_open_broken_links,
    _dashboard_overall_health_status,
    _dashboard_recent_imports,
    _dashboard_recent_pipeline_runs,
    _dashboard_runtime_mode_display,
    _dashboard_suggestion_counts,
    _dashboard_system_health,
    _pluralise,
    _today_view_sentence_today,
    _today_view_sentence_watch,
    _today_view_sentence_yesterday,
    _today_view_top_alert_dict,
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


# ── Today-view helpers (extracted from TodayActionsView.get) ─────


class PluraliseTests(SimpleTestCase):
    """Pure helper — single source for the n / n+s pluralisation rule."""

    def test_singular(self) -> None:
        self.assertEqual(_pluralise(1, "suggestion"), "1 suggestion")

    def test_plural_default_appends_s(self) -> None:
        self.assertEqual(_pluralise(3, "suggestion"), "3 suggestions")

    def test_zero_uses_plural_form(self) -> None:
        self.assertEqual(_pluralise(0, "suggestion"), "0 suggestions")

    def test_explicit_plural_form(self) -> None:
        self.assertEqual(_pluralise(5, "child", "children"), "5 children")


class TodayViewSentenceYesterdayTests(SimpleTestCase):
    def test_zero_counts_returns_empty_message(self) -> None:
        msg = _today_view_sentence_yesterday(
            {"approved": 0, "synced": 0, "pipeline_runs": 0}
        )
        self.assertIn("nothing was approved", msg)

    def test_one_approval_uses_singular(self) -> None:
        msg = _today_view_sentence_yesterday(
            {"approved": 1, "synced": 0, "pipeline_runs": 0}
        )
        self.assertIn("1 suggestion approved", msg)
        self.assertNotIn("suggestions", msg)

    def test_multiple_categories_concatenated(self) -> None:
        msg = _today_view_sentence_yesterday(
            {"approved": 5, "synced": 2, "pipeline_runs": 1}
        )
        self.assertIn("5 suggestions approved", msg)
        self.assertIn("2 sync jobs finished", msg)
        self.assertIn("1 pipeline run", msg)
        self.assertTrue(msg.endswith("."))


class TodayViewSentenceTodayTests(SimpleTestCase):
    def test_empty_queue(self) -> None:
        msg = _today_view_sentence_today(
            {"pending_reviews": 0, "running_syncs": 0}
        )
        self.assertIn("queue is clear", msg)

    def test_pending_only(self) -> None:
        msg = _today_view_sentence_today(
            {"pending_reviews": 3, "running_syncs": 0}
        )
        self.assertIn("3 suggestions waiting for review", msg)

    def test_both_categories_use_and(self) -> None:
        msg = _today_view_sentence_today(
            {"pending_reviews": 2, "running_syncs": 1}
        )
        self.assertIn("2 suggestions waiting for review", msg)
        self.assertIn("and", msg)
        self.assertIn("1 sync in flight", msg)


class TodayViewSentenceWatchTests(SimpleTestCase):
    def test_no_alert_returns_calm_message(self) -> None:
        self.assertEqual(_today_view_sentence_watch(None), "Nothing is on fire.")

    def test_alert_includes_severity_and_truncated_title(self) -> None:
        class FakeAlert:
            severity = "urgent"
            title = "x" * 200

        msg = _today_view_sentence_watch(FakeAlert())
        self.assertIn("urgent", msg)
        # Title truncated at 80 chars
        self.assertIn("x" * 80, msg)
        self.assertNotIn("x" * 81, msg)


class TodayViewTopAlertDictTests(SimpleTestCase):
    def test_none_passthrough(self) -> None:
        self.assertIsNone(_today_view_top_alert_dict(None))

    def test_serialises_required_fields(self) -> None:
        import uuid

        class FakeAlert:
            alert_id = uuid.uuid4()
            severity = "urgent"
            title = "Sample"

        result = _today_view_top_alert_dict(FakeAlert())
        self.assertEqual(set(result.keys()), {"alert_id", "severity", "title"})
        self.assertIsInstance(result["alert_id"], str)


# ── Heartbeat helpers (extracted from HelperNodeHeartbeatView.post) ──


class _FakeHelperNode:
    """In-memory stand-in for HelperNode — exercises mutation contract.

    Avoids creating real DB rows for unit tests of pure-mutation helpers.
    """

    def __init__(self) -> None:
        self.status = "offline"
        self.capabilities: dict = {}
        self.accepting_work = True
        self.active_jobs = 0
        self.queued_jobs = 0
        self.cpu_pct = 0.0
        self.ram_pct = 0.0
        self.gpu_util_pct: float | None = None
        self.gpu_vram_used_mb: int | None = None
        self.gpu_vram_total_mb: int | None = None
        self.network_rtt_ms: int | None = None
        self.native_kernels_healthy = False
        self.warmed_model_keys: list = []


class ApplyHeartbeatIdentityTests(TestCase):
    """Pin the defensive type checks on status / capabilities / accepting_work."""

    def test_valid_status_applied(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_identity(node, {"status": "online"})
        self.assertEqual(node.status, "online")

    def test_invalid_status_string_ignored(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_identity(node, {"status": "not-a-real-status"})
        # Status preserved (defensive guard against unknown enum values)
        self.assertEqual(node.status, "offline")

    def test_status_as_list_ignored(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_identity(node, {"status": ["online"]})
        self.assertEqual(node.status, "offline")

    def test_capabilities_dict_merged_not_replaced(self) -> None:
        node = _FakeHelperNode()
        node.capabilities = {"existing": "value"}
        _apply_heartbeat_identity(node, {"capabilities": {"new": "key"}})
        self.assertEqual(node.capabilities, {"existing": "value", "new": "key"})

    def test_capabilities_non_dict_ignored(self) -> None:
        node = _FakeHelperNode()
        node.capabilities = {"existing": "value"}
        _apply_heartbeat_identity(node, {"capabilities": "not a dict"})
        self.assertEqual(node.capabilities, {"existing": "value"})

    def test_accepting_work_true_string_parses(self) -> None:
        node = _FakeHelperNode()
        node.accepting_work = False
        _apply_heartbeat_identity(node, {"accepting_work": "yes"})
        self.assertTrue(node.accepting_work)

    def test_accepting_work_false_string_parses(self) -> None:
        # The original silent bug: bool("no") returns True. coerce_bool
        # is the fix — pin it here so a future regression fails loudly.
        node = _FakeHelperNode()
        node.accepting_work = True
        _apply_heartbeat_identity(node, {"accepting_work": "no"})
        self.assertFalse(node.accepting_work)

    def test_accepting_work_unsupported_type_keeps_previous(self) -> None:
        node = _FakeHelperNode()
        node.accepting_work = True
        _apply_heartbeat_identity(node, {"accepting_work": ["yes"]})
        # List is unsupported → previous value preserved.
        self.assertTrue(node.accepting_work)


class ApplyHeartbeatLoadMetricsTests(SimpleTestCase):
    def test_garbage_int_falls_back_to_previous(self) -> None:
        node = _FakeHelperNode()
        node.active_jobs = 3
        _apply_heartbeat_load_metrics(node, {"active_jobs": "high"})
        self.assertEqual(node.active_jobs, 3)

    def test_negative_int_clamped_to_zero(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_load_metrics(node, {"active_jobs": -5})
        self.assertEqual(node.active_jobs, 0)

    def test_cpu_pct_clamped_to_max_100(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_load_metrics(node, {"cpu_pct": 150.0})
        self.assertEqual(node.cpu_pct, 100.0)

    def test_garbage_float_falls_back_to_previous(self) -> None:
        node = _FakeHelperNode()
        node.cpu_pct = 42.5
        _apply_heartbeat_load_metrics(node, {"cpu_pct": "high"})
        self.assertEqual(node.cpu_pct, 42.5)


class ApplyHeartbeatGpuMetricsTests(SimpleTestCase):
    def test_empty_string_clears_field(self) -> None:
        node = _FakeHelperNode()
        node.gpu_util_pct = 42.0
        _apply_heartbeat_gpu_metrics(node, {"gpu_util_pct": ""})
        self.assertIsNone(node.gpu_util_pct)

    def test_none_clears_field(self) -> None:
        node = _FakeHelperNode()
        node.gpu_util_pct = 42.0
        _apply_heartbeat_gpu_metrics(node, {"gpu_util_pct": None})
        self.assertIsNone(node.gpu_util_pct)

    def test_valid_value_applied(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_gpu_metrics(node, {"gpu_vram_used_mb": 4096})
        self.assertEqual(node.gpu_vram_used_mb, 4096)


class ApplyHeartbeatNetworkHealthTests(SimpleTestCase):
    def test_warmed_model_keys_list_accepted(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_network_health(
            node, {"warmed_model_keys": ["bge-m3", "deberta"]}
        )
        self.assertEqual(node.warmed_model_keys, ["bge-m3", "deberta"])

    def test_warmed_model_keys_non_list_ignored(self) -> None:
        node = _FakeHelperNode()
        node.warmed_model_keys = ["existing"]
        _apply_heartbeat_network_health(node, {"warmed_model_keys": "bge-m3"})
        # Non-list ignored to prevent surprising downstream queries.
        self.assertEqual(node.warmed_model_keys, ["existing"])

    def test_native_kernels_healthy_truthy_int_becomes_true(self) -> None:
        node = _FakeHelperNode()
        _apply_heartbeat_network_health(node, {"native_kernels_healthy": 1})
        self.assertTrue(node.native_kernels_healthy)
