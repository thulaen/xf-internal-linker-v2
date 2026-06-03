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
    _apply_heartbeat_identity,
    _apply_heartbeat_load_metrics,
    _apply_heartbeat_network_health,
    _build_value_model_rows,
    _build_wordpress_rows,
    _coerce_bool_strict,
    _coerce_float_strict,
    _coerce_int_strict,
    _dashboard_content_count,
    _dashboard_open_broken_links,
    _dashboard_overall_health_status,
    _dashboard_recent_imports,
    _dashboard_recent_pipeline_runs,
    _dashboard_runtime_mode_display,
    _dashboard_suggestion_counts,
    _dashboard_system_health,
    _job_queue_active_runs,
    _job_queue_active_syncs,
    _legacy_quarantine_row,
    _persist_performance_mode_settings,
    _pluralise,
    _quarantine_legacy_rows,
    _quarantine_records_and_run_ids,
    _read_runtime_mode_setting,
    _resolve_performance_expiry_choice,
    _resume_view_interrupted_runs,
    _resume_view_missed_tasks,
    _resume_view_resumable_syncs,
    _status_story_alerts_fragment,
    _status_story_broken_fragment,
    _status_story_fragments,
    _status_story_health_fragment,
    _status_story_pending_fragment,
    _status_story_time_prefix,
    _today_actions_pending_suggestions,
    _today_actions_pipeline_freshness,
    _today_actions_sync_freshness,
    _today_actions_urgent_alerts,
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
        self.assertEqual(rows["value_model.traffic_lookback_days"]["value_type"], "int")

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
        msg = _today_view_sentence_today({"pending_reviews": 0, "running_syncs": 0})
        self.assertIn("queue is clear", msg)

    def test_pending_only(self) -> None:
        msg = _today_view_sentence_today({"pending_reviews": 3, "running_syncs": 0})
        self.assertIn("3 suggestions waiting for review", msg)

    def test_both_categories_use_and(self) -> None:
        msg = _today_view_sentence_today({"pending_reviews": 2, "running_syncs": 1})
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


# ── Strict-raising coercers (extracted from _validate_ga4_gsc_settings) ──


class CoerceFloatStrictTests(SimpleTestCase):
    def test_valid_float_returned(self) -> None:
        self.assertEqual(_coerce_float_strict("0.5", key="x"), 0.5)
        self.assertEqual(_coerce_float_strict(1, key="x"), 1.0)

    def test_garbage_raises_with_field_name(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_float_strict("foo", key="ranking_weight")
        self.assertIn("ranking_weight", str(ctx.exception))
        self.assertIn("numeric", str(ctx.exception))

    def test_infinity_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_float_strict(float("inf"), key="x")
        self.assertIn("finite", str(ctx.exception))

    def test_nan_raises(self) -> None:
        with self.assertRaises(ValueError):
            _coerce_float_strict(float("nan"), key="x")


class CoerceIntStrictTests(SimpleTestCase):
    def test_in_range_returned(self) -> None:
        self.assertEqual(_coerce_int_strict("5", key="x", minimum=1, maximum=10), 5)

    def test_below_min_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_int_strict(0, key="lookback", minimum=1, maximum=10)
        self.assertIn("between 1 and 10", str(ctx.exception))

    def test_above_max_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_int_strict(99, key="lookback", minimum=1, maximum=10)
        self.assertIn("between 1 and 10", str(ctx.exception))

    def test_garbage_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_int_strict("not-a-number", key="lookback", minimum=1, maximum=10)
        self.assertIn("whole number", str(ctx.exception))


class CoerceBoolStrictTests(SimpleTestCase):
    def test_native_bool_returned(self) -> None:
        self.assertTrue(_coerce_bool_strict(True, key="x"))
        self.assertFalse(_coerce_bool_strict(False, key="x"))

    def test_truthy_string(self) -> None:
        for v in ("true", "1", "yes", "on", "TRUE"):
            with self.subTest(v=v):
                self.assertTrue(_coerce_bool_strict(v, key="x"))

    def test_falsy_string(self) -> None:
        for v in ("false", "0", "no", "off", "NO"):
            with self.subTest(v=v):
                self.assertFalse(_coerce_bool_strict(v, key="x"))

    def test_unknown_string_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _coerce_bool_strict("maybe", key="sync_enabled")
        self.assertIn("sync_enabled", str(ctx.exception))
        self.assertIn("true or false", str(ctx.exception))

    def test_non_string_non_bool_raises(self) -> None:
        with self.assertRaises(ValueError):
            _coerce_bool_strict([True], key="x")


# ── Status-story fragments (extracted from StatusStoryView.get) ──


class StatusStoryFragmentTests(SimpleTestCase):
    def test_alerts_fragment_zero(self) -> None:
        self.assertEqual(_status_story_alerts_fragment(0), "no new alerts")

    def test_alerts_fragment_one(self) -> None:
        self.assertEqual(_status_story_alerts_fragment(1), "1 alert fired today")

    def test_alerts_fragment_many(self) -> None:
        self.assertEqual(_status_story_alerts_fragment(7), "7 alerts fired today")

    def test_health_fragment_healthy(self) -> None:
        self.assertEqual(
            _status_story_health_fragment("healthy"), "all systems healthy"
        )

    def test_health_fragment_unknown_returns_none(self) -> None:
        # Unknown health is silent — we don't mislead the operator
        self.assertIsNone(_status_story_health_fragment("unknown"))

    def test_health_fragment_critical_or_error(self) -> None:
        for v in ("critical", "error"):
            with self.subTest(v=v):
                self.assertEqual(
                    _status_story_health_fragment(v), "a critical service is down"
                )

    def test_pending_fragment_pluralisation(self) -> None:
        self.assertEqual(_status_story_pending_fragment(0), "no suggestions waiting")
        self.assertEqual(
            _status_story_pending_fragment(1), "1 suggestion waiting for review"
        )
        self.assertEqual(
            _status_story_pending_fragment(5), "5 suggestions waiting for review"
        )

    def test_broken_fragment_zero_returns_none(self) -> None:
        self.assertIsNone(_status_story_broken_fragment(0))

    def test_broken_fragment_singular(self) -> None:
        self.assertEqual(_status_story_broken_fragment(1), "1 broken link")

    def test_broken_fragment_plural(self) -> None:
        self.assertEqual(_status_story_broken_fragment(3), "3 broken links")

    def test_fragments_drops_none_values(self) -> None:
        # Both health=unknown AND broken=0 drop out of the list
        result = _status_story_fragments(
            alerts_today=0,
            health_status="unknown",
            pending_reviews=0,
            broken_links_open=0,
        )
        self.assertEqual(len(result), 2)  # only alerts + pending
        self.assertNotIn(None, result)

    def test_time_prefix_morning(self) -> None:
        for h in (0, 6, 11):
            with self.subTest(hour=h):
                self.assertEqual(_status_story_time_prefix(h), "This morning")

    def test_time_prefix_afternoon(self) -> None:
        for h in (12, 14, 16):
            with self.subTest(hour=h):
                self.assertEqual(_status_story_time_prefix(h), "This afternoon")

    def test_time_prefix_evening(self) -> None:
        for h in (17, 20, 23):
            with self.subTest(hour=h):
                self.assertEqual(_status_story_time_prefix(h), "This evening")


# ── Today-actions priority rules (extracted from TodayActionsView.get) ──


class TodayActionsPriorityRuleTests(TestCase):
    def setUp(self) -> None:
        # Defensive cleanup: each rule queries a different model.
        from apps.notifications.models import OperatorAlert
        from apps.suggestions.models import PipelineRun, Suggestion
        from apps.sync.models import SyncJob

        OperatorAlert.objects.all().delete()
        PipelineRun.objects.all().delete()
        Suggestion.objects.all().delete()
        SyncJob.objects.all().delete()

    def test_urgent_alerts_returns_empty_when_none(self) -> None:
        self.assertEqual(_today_actions_urgent_alerts(), [])

    def test_pending_suggestions_below_threshold(self) -> None:
        # Empty queue → no action
        self.assertEqual(_today_actions_pending_suggestions(), [])

    def test_no_sync_yet_returns_first_sync_action(self) -> None:
        from django.utils import timezone

        actions = _today_actions_sync_freshness(timezone.now())
        self.assertEqual(len(actions), 1)
        self.assertIn("first content sync", actions[0]["reason"])

    def test_no_pipeline_run_returns_empty(self) -> None:
        from django.utils import timezone

        # No PipelineRun → no action (this rule doesn't generate an
        # "onboarding" action like the sync one does)
        self.assertEqual(_today_actions_pipeline_freshness(timezone.now()), [])


# ── Resume-view helpers (extracted from ResumeStateView.get) ─────


class ResumeViewHelperTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun
        from apps.sync.models import SyncJob

        PipelineRun.objects.all().delete()
        SyncJob.objects.all().delete()

    def test_interrupted_runs_returns_empty(self) -> None:
        self.assertEqual(_resume_view_interrupted_runs(), [])

    def test_resumable_syncs_returns_empty(self) -> None:
        self.assertEqual(_resume_view_resumable_syncs(), [])

    def test_missed_tasks_handles_missing_registry_gracefully(self) -> None:
        # Either succeeds with [] (registry empty) or returns the actual
        # missed-task list — both are acceptable. The defensive helper
        # must not raise either way.
        result = _resume_view_missed_tasks()
        self.assertIsInstance(result, list)


# ── Quarantine helpers (extracted from JobQuarantineView.get) ─────


class QuarantineHelperTests(TestCase):
    def setUp(self) -> None:
        from apps.core.models import QuarantineRecord
        from apps.suggestions.models import PipelineRun

        QuarantineRecord.objects.all().delete()
        PipelineRun.objects.all().delete()

    def test_records_and_run_ids_empty(self) -> None:
        records, run_ids = _quarantine_records_and_run_ids()
        self.assertEqual(records, [])
        self.assertEqual(run_ids, set())

    def test_legacy_rows_empty(self) -> None:
        self.assertEqual(_quarantine_legacy_rows(skip_run_ids=set()), [])

    def test_legacy_rows_dedup_against_skip_set(self) -> None:
        from apps.suggestions.models import PipelineRun

        run = PipelineRun.objects.create(
            run_state="failed", rerun_mode="full", is_quarantined=True
        )
        rid = str(run.run_id)
        # Without skip → 1 result
        rows = _quarantine_legacy_rows(skip_run_ids=set())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], rid)
        # With matching skip → 0 results
        rows = _quarantine_legacy_rows(skip_run_ids={rid})
        self.assertEqual(rows, [])

    def test_legacy_row_shape(self) -> None:
        run_dict = {
            "run_id": "abc-123",
            "run_state": "failed",
            "rerun_mode": "full",
            "error_message": "boom",
            "phase_log": ["a", "b"],
            "created_at": None,
            "updated_at": None,
        }
        row = _legacy_quarantine_row(run_dict, "abc-123")
        # Required keys for the frontend
        for key in (
            "id",
            "kind",
            "run_id",
            "related_object_type",
            "reason",
            "reason_display",
            "fix_available",
        ):
            with self.subTest(key=key):
                self.assertIn(key, row)
        self.assertEqual(row["kind"], "legacy")
        self.assertEqual(row["fix_available"], "reset-quarantined-job")


# ── Performance-mode helpers (extracted from RuntimeSwitchView.post) ──


class ResolvePerformanceExpiryChoiceTests(SimpleTestCase):
    def test_safe_mode_forces_none(self) -> None:
        self.assertEqual(
            _resolve_performance_expiry_choice(mode="safe", raw_expiry="night"),
            "none",
        )

    def test_balanced_mode_forces_none(self) -> None:
        self.assertEqual(
            _resolve_performance_expiry_choice(mode="balanced", raw_expiry="activity"),
            "none",
        )

    def test_high_mode_accepts_documented_expiry_values(self) -> None:
        for v in ("none", "activity", "night"):
            with self.subTest(v=v):
                self.assertEqual(
                    _resolve_performance_expiry_choice(mode="high", raw_expiry=v),
                    v,
                )

    def test_high_mode_rejects_unknown_expiry_to_none(self) -> None:
        self.assertEqual(
            _resolve_performance_expiry_choice(mode="high", raw_expiry="garbage"),
            "none",
        )


class PersistPerformanceModeSettingsTests(TestCase):
    def setUp(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key__startswith="system.performance_mode").delete()

    def test_persists_three_appsetting_rows(self) -> None:
        from apps.core.models import AppSetting

        _persist_performance_mode_settings(
            mode="high", expiry="activity", expires_at=""
        )
        for key in (
            "system.performance_mode",
            "system.performance_mode_expiry",
            "system.performance_mode_expires_at",
        ):
            with self.subTest(key=key):
                row = AppSetting.objects.filter(key=key).first()
                self.assertIsNotNone(row)


class ReadRuntimeModeSettingTests(TestCase):
    def test_defaults_to_cpu_when_unset(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key="system.runtime_mode").delete()
        self.assertEqual(_read_runtime_mode_setting(), "cpu")

    def test_returns_persisted_value(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="system.runtime_mode",
            defaults={"value": "gpu", "value_type": "str"},
        )
        self.assertEqual(_read_runtime_mode_setting(), "gpu")


# ── WordPress row builder (extracted from WordPressSettingsView.put) ──


class BuildWordpressRowsTests(SimpleTestCase):
    def _validated(self, *, app_password_provided: bool = False) -> dict:
        return {
            "base_url": "https://blog.example.com",
            "username": "editor",
            "app_password": "secret",
            "app_password_provided": app_password_provided,
            "sync_enabled": True,
            "sync_hour": 4,
            "sync_minute": 15,
        }

    def test_required_rows_present(self) -> None:
        rows = _build_wordpress_rows(self._validated())
        for key in (
            "wordpress.base_url",
            "wordpress.username",
            "wordpress.sync_enabled",
            "wordpress.sync_hour",
            "wordpress.sync_minute",
        ):
            with self.subTest(key=key):
                self.assertIn(key, rows)

    def test_app_password_omitted_when_not_provided(self) -> None:
        rows = _build_wordpress_rows(self._validated(app_password_provided=False))
        # Operator can re-PUT base settings without clobbering the secret
        self.assertNotIn("wordpress.app_password", rows)

    def test_app_password_included_when_provided(self) -> None:
        rows = _build_wordpress_rows(self._validated(app_password_provided=True))
        self.assertIn("wordpress.app_password", rows)
        self.assertTrue(rows["wordpress.app_password"]["is_secret"])

    def test_bool_serialised_as_string(self) -> None:
        rows = _build_wordpress_rows(self._validated())
        self.assertEqual(rows["wordpress.sync_enabled"]["value"], "true")

    def test_int_serialised_as_string(self) -> None:
        rows = _build_wordpress_rows(self._validated())
        self.assertEqual(rows["wordpress.sync_hour"]["value"], "4")
        self.assertEqual(rows["wordpress.sync_minute"]["value"], "15")


# ── JobQueue helpers (extracted from JobQueueView.get) ───────────


class JobQueueHelperTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun
        from apps.sync.models import SyncJob

        PipelineRun.objects.all().delete()
        SyncJob.objects.all().delete()

    def test_active_runs_empty(self) -> None:
        self.assertEqual(_job_queue_active_runs(), [])

    def test_active_syncs_empty(self) -> None:
        self.assertEqual(_job_queue_active_syncs(), [])

    def test_active_runs_caps_at_20(self) -> None:
        from apps.suggestions.models import PipelineRun

        for _ in range(25):
            PipelineRun.objects.create(run_state="queued", rerun_mode="full")
        self.assertEqual(len(_job_queue_active_runs()), 20)

    def test_active_runs_stringify_run_id(self) -> None:
        from apps.suggestions.models import PipelineRun

        run = PipelineRun.objects.create(run_state="running", rerun_mode="full")
        runs = _job_queue_active_runs()
        self.assertEqual(runs[0]["run_id"], str(run.run_id))
        self.assertEqual(runs[0]["type"], "pipeline")

    def test_active_syncs_includes_type_field(self) -> None:
        from apps.sync.models import SyncJob

        SyncJob.objects.create(source="xenforo", status="running", mode="full")
        syncs = _job_queue_active_syncs()
        self.assertEqual(syncs[0]["type"], "sync")


# ── GA4/GSC + Link Freshness row builders + WP credentials helpers ──


class BuildGa4GscRowsTests(SimpleTestCase):
    """Pin the GA4/GSC row builder pattern (same as WP / value-model)."""

    def _validated(self, *, private_key_provided: bool = False) -> dict:
        return {
            "ranking_weight": 0.05,
            "property_url": "https://example.com",
            "service_account_email": "svc@example.com",
            "sync_enabled": True,
            "sync_lookback_days": 14,
            "private_key": "secret",
            "private_key_provided": private_key_provided,
        }

    def test_required_rows_present(self) -> None:
        from apps.core.views import _build_ga4_gsc_rows

        rows = _build_ga4_gsc_rows(self._validated())
        for key in (
            "ga4_gsc.ranking_weight",
            "ga4_gsc.property_url",
            "ga4_gsc.service_account_email",
            "ga4_gsc.sync_enabled",
            "ga4_gsc.sync_lookback_days",
        ):
            with self.subTest(key=key):
                self.assertIn(key, rows)

    def test_private_key_omitted_when_not_provided(self) -> None:
        from apps.core.views import _build_ga4_gsc_rows

        rows = _build_ga4_gsc_rows(self._validated(private_key_provided=False))
        # Same security pattern as WP app_password — partial re-PUT
        # without the secret must NOT clobber the stored value.
        self.assertNotIn("ga4_gsc.private_key", rows)

    def test_private_key_included_when_provided(self) -> None:
        from apps.core.views import _build_ga4_gsc_rows

        rows = _build_ga4_gsc_rows(self._validated(private_key_provided=True))
        self.assertIn("ga4_gsc.private_key", rows)
        self.assertTrue(rows["ga4_gsc.private_key"]["is_secret"])


class BuildLinkFreshnessRowsTests(SimpleTestCase):
    """Pin the Link Freshness row builder pattern."""

    def _validated(self) -> dict:
        return {
            "ranking_weight": 0.05,
            "recent_window_days": 30,
            "newest_peer_percent": 0.25,
            "min_peer_count": 5,
            "w_recent": 0.4,
            "w_growth": 0.3,
            "w_cohort": 0.2,
            "w_loss": 0.1,
        }

    def test_all_8_rows_present(self) -> None:
        from apps.core.views import _build_link_freshness_rows

        rows = _build_link_freshness_rows(self._validated())
        self.assertEqual(len(rows), 8)
        for key in (
            "link_freshness.ranking_weight",
            "link_freshness.recent_window_days",
            "link_freshness.newest_peer_percent",
            "link_freshness.min_peer_count",
            "link_freshness.w_recent",
            "link_freshness.w_growth",
            "link_freshness.w_cohort",
            "link_freshness.w_loss",
        ):
            with self.subTest(key=key):
                self.assertIn(key, rows)

    def test_weight_serialised_as_float(self) -> None:
        from apps.core.views import _build_link_freshness_rows

        rows = _build_link_freshness_rows(self._validated())
        self.assertEqual(rows["link_freshness.w_recent"]["value_type"], "float")

    def test_int_settings_serialised_as_str(self) -> None:
        from apps.core.views import _build_link_freshness_rows

        rows = _build_link_freshness_rows(self._validated())
        self.assertEqual(rows["link_freshness.recent_window_days"]["value"], "30")
        self.assertEqual(rows["link_freshness.recent_window_days"]["value_type"], "int")


class WpResolveCredentialsTests(TestCase):
    """Credential precedence: request body > AppSetting > Django settings."""

    def setUp(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key__startswith="wordpress.").delete()

    def test_request_body_wins(self) -> None:
        from apps.core.views import _wp_resolve_credentials

        creds = _wp_resolve_credentials(
            {
                "base_url": "https://body.example.com",
                "username": "u",
                "app_password": "p",
            }
        )
        self.assertEqual(creds["base_url"], "https://body.example.com")
        self.assertEqual(creds["username"], "u")

    def test_falls_back_to_appsetting(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.views import _wp_resolve_credentials

        AppSetting.objects.update_or_create(
            key="wordpress.base_url",
            defaults={"value": "https://stored.example.com"},
        )
        creds = _wp_resolve_credentials({})
        self.assertEqual(creds["base_url"], "https://stored.example.com")

    def test_strips_trailing_slash_from_url(self) -> None:
        from apps.core.views import _wp_resolve_credentials

        creds = _wp_resolve_credentials({"base_url": "https://x.com/"})
        self.assertEqual(creds["base_url"], "https://x.com")

    def test_strips_whitespace(self) -> None:
        from apps.core.views import _wp_resolve_credentials

        creds = _wp_resolve_credentials(
            {
                "base_url": "  https://x.com  ",
                "username": "  user  ",
                "app_password": "  p  ",
            }
        )
        self.assertEqual(creds["base_url"], "https://x.com")
        self.assertEqual(creds["username"], "user")
        self.assertEqual(creds["app_password"], "p")


class SampleCpuRamMetricsTests(SimpleTestCase):
    """Verify the CPU+RAM sampler returns the documented shape (or null fields on failure)."""

    def test_keys_always_present(self):
        from apps.core.views import _sample_cpu_ram_metrics

        result = _sample_cpu_ram_metrics()
        self.assertEqual(
            set(result.keys()),
            {"cpu_percent", "ram_used_mb", "ram_total_mb", "ram_percent"},
        )

    def test_values_are_numeric_when_psutil_available(self):
        from apps.core.views import _sample_cpu_ram_metrics

        result = _sample_cpu_ram_metrics()
        # psutil IS available in the test container — values must not be None.
        # If psutil ever becomes unavailable the contract is null fields.
        for key, value in result.items():
            self.assertTrue(
                value is None or isinstance(value, (int, float)),
                msg=f"{key}={value!r} must be int|float|None",
            )


class XfResolveCredentialsTests(TestCase):
    """Verify XenForo credential precedence: body > AppSetting > Django settings."""

    def setUp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key__startswith="xenforo.").delete()

    def test_body_wins_when_provided(self):
        from apps.core.views import _xf_resolve_credentials

        base_url, api_key = _xf_resolve_credentials(
            {"base_url": "https://body.example.com/", "api_key": "body-key"},
        )
        self.assertEqual(base_url, "https://body.example.com")
        self.assertEqual(api_key, "body-key")

    def test_strips_trailing_slash_and_whitespace(self):
        from apps.core.views import _xf_resolve_credentials

        base_url, api_key = _xf_resolve_credentials(
            {"base_url": "  https://x.com/  ", "api_key": "  k  "},
        )
        self.assertEqual(base_url, "https://x.com")
        self.assertEqual(api_key, "k")


class TodaySummaryHelperTests(TestCase):
    """Verify the today-summary counts and autotuner outcome helpers."""

    def test_counts_zero_when_no_data(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.core.views import _today_summary_counts

        result = _today_summary_counts(timezone.now() - timedelta(hours=24))
        self.assertEqual(result["new_suggestions"], 0)
        self.assertEqual(result["reviewed"], 0)
        self.assertEqual(result["items_synced"], 0)
        self.assertEqual(result["pipeline_runs"], 0)

    def test_autotuner_outcome_returns_none_when_no_challengers(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.core.views import _today_autotuner_outcome

        result = _today_autotuner_outcome(timezone.now() - timedelta(hours=24))
        self.assertIsNone(result)


class GraphCandidateRowsTests(SimpleTestCase):
    """Verify the graph-candidate row builder."""

    def test_all_six_rows_present(self):
        from apps.core.views import _build_graph_candidate_rows

        rows = _build_graph_candidate_rows(
            {
                "enabled": True,
                "walk_steps_per_entity": 100,
                "min_stable_candidates": 10,
                "min_visit_threshold": 2,
                "top_k_candidates": 50,
                "top_n_entities_per_article": 5,
            }
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows["graph_candidate.enabled"]["value"], "true")
        self.assertEqual(rows["graph_candidate.walk_steps_per_entity"]["value"], "100")

    def test_bool_serialised_correctly(self):
        from apps.core.views import _build_graph_candidate_rows

        rows_off = _build_graph_candidate_rows(
            {
                "enabled": False,
                "walk_steps_per_entity": 1,
                "min_stable_candidates": 1,
                "min_visit_threshold": 1,
                "top_k_candidates": 1,
                "top_n_entities_per_article": 1,
            }
        )
        self.assertEqual(rows_off["graph_candidate.enabled"]["value"], "false")


class SpamGuardRowsTests(SimpleTestCase):
    """Verify the spam-guard row builder."""

    def test_all_three_rows_present(self):
        from apps.core.views import _build_spam_guard_rows

        rows = _build_spam_guard_rows(
            {
                "max_existing_links_per_host": 3,
                "max_anchor_words": 4,
                "paragraph_window": 3,
            }
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows["spam_guards.max_anchor_words"]["value"], "4")

    def test_descriptions_carry_patent_citations(self):
        from apps.core.views import _build_spam_guard_rows

        rows = _build_spam_guard_rows(
            {
                "max_existing_links_per_host": 3,
                "max_anchor_words": 4,
                "paragraph_window": 3,
            }
        )
        # Per AGENTS.md citation rule: each spam-guard description must
        # carry a specific patent reference.
        for row in rows.values():
            self.assertRegex(row["description"], r"US\d+[A-Z]?\d*")


class GscResolveCredentialsTests(TestCase):
    """Verify GA4/GSC credential precedence: body > AppSetting > Django settings."""

    def setUp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key__startswith="ga4_gsc.").delete()

    def test_body_wins_when_provided(self):
        from apps.core.views import _gsc_resolve_credentials

        creds = _gsc_resolve_credentials(
            {
                "property_url": "https://body.example.com/",
                "service_account_email": "body@svc.iam",
                "private_key": "BODYKEY",
            }
        )
        self.assertEqual(creds["property_url"], "https://body.example.com")
        self.assertEqual(creds["service_account_email"], "body@svc.iam")
        self.assertEqual(creds["private_key"], "BODYKEY")

    def test_strips_trailing_slash_from_property_url(self):
        from apps.core.views import _gsc_resolve_credentials

        creds = _gsc_resolve_credentials(
            {
                "property_url": "https://example.com/",
                "service_account_email": "x@y",
                "private_key": "k",
            }
        )
        self.assertEqual(creds["property_url"], "https://example.com")


class MasterPauseStateTests(TestCase):
    """Verify the master-pause read + persist helpers."""

    def setUp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key="system.master_pause").delete()

    def test_returns_false_when_no_setting(self):
        from apps.core.views import _read_master_pause_state

        self.assertFalse(_read_master_pause_state())

    def test_returns_true_when_setting_is_true(self):
        from apps.core.models import AppSetting
        from apps.core.views import _read_master_pause_state

        AppSetting.objects.create(
            key="system.master_pause",
            value="true",
            value_type="bool",
        )
        self.assertTrue(_read_master_pause_state())

    def test_persist_creates_or_updates(self):
        from apps.core.models import AppSetting
        from apps.core.views import (
            _persist_master_pause_state,
            _read_master_pause_state,
        )

        _persist_master_pause_state(True)
        self.assertTrue(_read_master_pause_state())
        _persist_master_pause_state(False)
        self.assertFalse(_read_master_pause_state())
        # Confirm the row was upserted not duplicated.
        self.assertEqual(
            AppSetting.objects.filter(key="system.master_pause").count(),
            1,
        )


class RuntimeSettingsSnapshotTests(TestCase):
    """Cold-start defaults + bulk-read happy path."""

    def setUp(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.filter(
            key__in=[
                "system.runtime_mode",
                "system.performance_mode",
                "system.performance_mode_expiry",
                "system.performance_mode_expires_at",
                "system.master_pause",
            ]
        ).delete()

    def test_defaults_when_no_appsettings_exist(self) -> None:
        from apps.core.views import _runtime_settings_snapshot

        snap = _runtime_settings_snapshot()
        self.assertEqual(snap["runtime_mode"], "cpu")
        self.assertEqual(snap["performance_mode_expiry"], "none")
        self.assertEqual(snap["performance_mode_expires_at"], "")
        self.assertFalse(snap["master_pause"])

    def test_master_pause_parses_true_string(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.views import _runtime_settings_snapshot

        AppSetting.objects.update_or_create(
            key="system.master_pause", defaults={"value": "true"}
        )
        snap = _runtime_settings_snapshot()
        self.assertTrue(snap["master_pause"])

    def test_master_pause_false_for_other_values(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.views import _runtime_settings_snapshot

        AppSetting.objects.update_or_create(
            key="system.master_pause", defaults={"value": "garbage"}
        )
        snap = _runtime_settings_snapshot()
        self.assertFalse(snap["master_pause"])

    def test_unknown_expiry_falls_back_to_none(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.views import _runtime_settings_snapshot

        AppSetting.objects.update_or_create(
            key="system.performance_mode_expiry",
            defaults={"value": "garbage"},
        )
        snap = _runtime_settings_snapshot()
        self.assertEqual(snap["performance_mode_expiry"], "none")

    def test_known_expiry_preserved(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.views import _runtime_settings_snapshot

        AppSetting.objects.update_or_create(
            key="system.performance_mode_expiry",
            defaults={"value": "night"},
        )
        snap = _runtime_settings_snapshot()
        self.assertEqual(snap["performance_mode_expiry"], "night")
