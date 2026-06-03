"""Tests for the pure-function helpers extracted from health/services.py.

These helpers replaced ~700 lines of repeated try/except/return boilerplate
across the 16 ``check_*_health`` functions. Each helper is independently
testable in ``SimpleTestCase`` (no DB), so a future tweak to one branch's
wording or threshold can be locked in here without spinning up Django.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.health.models import ServiceHealthRecord
from apps.health.services import (
    _build_model_runtime_metadata,
    _check_metric_freshness,
    _classify_celery_beat_state,
    _classify_celery_queue_depth,
    _classify_crawler_session_state,
    _classify_disk_space,
    _classify_helper_nodes_state,
    _classify_pipeline_state,
    _make_check_failed_result,
    _make_health_result,
    _model_runtime_result,
    _pick_model_runtime_state_key,
    _SearchMetricCheckConfig,
)


class MakeHealthResultTests(SimpleTestCase):
    """Verify the generic ServiceHealthResult builder."""

    def test_success_sets_last_success_at(self):
        result = _make_health_result(
            "x",
            status="healthy",
            label="ok",
            issue="",
            fix="",
            success=True,
        )
        self.assertEqual(result.service_key, "x")
        self.assertEqual(result.status, "healthy")
        self.assertIsNotNone(result.last_success_at)
        self.assertIsNone(result.last_error_at)

    def test_failure_sets_last_error_at(self):
        result = _make_health_result(
            "x",
            status="error",
            label="bad",
            issue="i",
            fix="f",
            success=False,
        )
        self.assertIsNone(result.last_success_at)
        self.assertIsNotNone(result.last_error_at)

    def test_metadata_passes_through(self):
        result = _make_health_result(
            "x",
            status="healthy",
            label="ok",
            issue="",
            fix="",
            metadata={"a": 1},
        )
        self.assertEqual(result.metadata, {"a": 1})


class MakeCheckFailedResultTests(SimpleTestCase):
    """Verify the standardised "check itself crashed" result."""

    def test_returns_error_status(self):
        exc = RuntimeError("boom")
        result = _make_check_failed_result(
            "x", exc, label="X failed.", fix="Try again."
        )
        self.assertEqual(result.status, ServiceHealthRecord.STATUS_ERROR)
        self.assertEqual(result.status_label, "X failed.")
        self.assertIn("boom", result.issue_description)
        self.assertEqual(result.last_error_message, "boom")
        self.assertIsNotNone(result.last_error_at)


class ModelRuntimeResultTests(SimpleTestCase):
    """Verify the model-runtime branch builder uses the right service_key."""

    def test_service_key_is_model_runtime(self):
        result = _model_runtime_result(
            {"a": 1},
            status="healthy",
            label="ok",
            issue="",
            fix="",
        )
        self.assertEqual(result.service_key, "model_runtime")
        self.assertEqual(result.metadata, {"a": 1})


class BuildModelRuntimeMetadataTests(SimpleTestCase):
    """Verify metadata flattens the model-registry summary correctly."""

    def test_all_keys_present(self):
        meta = _build_model_runtime_metadata(
            summary={"hot_swap_safe": True, "reclaimable_disk_bytes": 100},
            active_model={"dimension": 768},
            candidate_model={"model_name": "cand", "status": "warming"},
            backfill={"status": "running", "progress_pct": 42},
            active_name="bge-m3",
            device_target="cuda:0",
        )
        self.assertEqual(meta["active_model"], "bge-m3")
        self.assertEqual(meta["active_dimension"], 768)
        self.assertEqual(meta["candidate_model"], "cand")
        self.assertEqual(meta["candidate_status"], "warming")
        self.assertTrue(meta["hot_swap_safe"])
        self.assertEqual(meta["reclaimable_disk_bytes"], 100)
        self.assertEqual(meta["backfill_status"], "running")
        self.assertEqual(meta["backfill_progress_pct"], 42)


class PickModelRuntimeStateKeyTests(SimpleTestCase):
    """Verify the state-key picker matches the documented decision tree."""

    def test_no_active_model(self):
        self.assertEqual(
            _pick_model_runtime_state_key({}, {}, {}, "unknown"),
            "no_active",
        )

    def test_failed_active(self):
        self.assertEqual(
            _pick_model_runtime_state_key({"id": 1}, {}, {}, "failed"),
            "failed_or_deleted",
        )

    def test_swap_in_progress(self):
        self.assertEqual(
            _pick_model_runtime_state_key(
                {"id": 1},
                {},
                {"status": "running"},
                "ready",
            ),
            "swap_in_progress",
        )

    def test_candidate_waiting(self):
        self.assertEqual(
            _pick_model_runtime_state_key(
                {"id": 1},
                {"id": 2},
                {},
                "ready",
            ),
            "candidate_waiting",
        )

    def test_healthy(self):
        self.assertEqual(
            _pick_model_runtime_state_key({"id": 1}, {}, {}, "ready"),
            "healthy",
        )


class ClassifyHelperNodesStateTests(SimpleTestCase):
    """Verify helper-nodes status-table lookups."""

    def test_no_helpers_registered(self):
        decision = _classify_helper_nodes_state(0, 0, 0, 0, 0.0)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_NOT_CONFIGURED)
        self.assertEqual(decision["label"], "No helper nodes configured.")
        # Exact fix copy after GPU/CUDA removal — pins the string mutmut would
        # otherwise wrap (the line dropped "or GPU-heavy" on this diff).
        self.assertEqual(
            decision["fix"],
            "Open Settings > Helpers to register a helper node if you want "
            "to offload RAM-heavy background work.",
        )
        self.assertNotIn("GPU", decision["fix"])
        self.assertTrue(decision["success"])

    def test_all_offline(self):
        decision = _classify_helper_nodes_state(0, 0, 0, 5, 0.0)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)
        self.assertIn("offline", decision["label"])

    def test_all_stale(self):
        decision = _classify_helper_nodes_state(0, 0, 5, 0, 0.0)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)
        self.assertIn("stale", decision["label"])

    def test_high_ram_pressure(self):
        decision = _classify_helper_nodes_state(2, 1, 0, 0, 0.95)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)
        self.assertIn("RAM", decision["label"])

    def test_healthy(self):
        decision = _classify_helper_nodes_state(2, 1, 0, 0, 0.5)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)
        self.assertIn("2 online", decision["label"])


class ClassifyDiskSpaceTests(SimpleTestCase):
    """Verify disk-space wording at three thresholds."""

    def test_critical_at_high_usage(self):
        decision = _classify_disk_space(
            free_gb=5.0,
            total_gb=100.0,
            usage_pct=95.0,
            warn_pct=80,
            error_pct=90,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_ERROR)

    def test_warning_at_medium_usage(self):
        decision = _classify_disk_space(
            free_gb=20.0,
            total_gb=100.0,
            usage_pct=85.0,
            warn_pct=80,
            error_pct=90,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)

    def test_healthy_at_low_usage(self):
        decision = _classify_disk_space(
            free_gb=60.0,
            total_gb=100.0,
            usage_pct=40.0,
            warn_pct=80,
            error_pct=90,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)


class ClassifyCeleryQueueDepthTests(SimpleTestCase):
    """Verify queue-depth wording at three thresholds."""

    def test_overflow(self):
        decision = _classify_celery_queue_depth(
            "default",
            250,
            250,
            warn_threshold=50,
            error_threshold=200,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_ERROR)

    def test_building_up(self):
        decision = _classify_celery_queue_depth(
            "default",
            75,
            75,
            warn_threshold=50,
            error_threshold=200,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)

    def test_clear(self):
        decision = _classify_celery_queue_depth(
            "default",
            5,
            5,
            warn_threshold=50,
            error_threshold=200,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)


class ClassifyCeleryBeatStateTests(SimpleTestCase):
    """Verify beat-freshness wording at three thresholds."""

    def test_stale(self):
        # 60min threshold * 1.5 = 90min; 100min ago = STALE error
        decision = _classify_celery_beat_state(minutes_ago=100.0, stale_minutes=60)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_ERROR)

    def test_delayed(self):
        # 60min < 70min < 90min = DELAYED warning
        decision = _classify_celery_beat_state(minutes_ago=70.0, stale_minutes=60)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)

    def test_healthy(self):
        decision = _classify_celery_beat_state(minutes_ago=15.0, stale_minutes=60)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)


class ClassifyPipelineStateTests(SimpleTestCase):
    """Verify pipeline-failure wording at three thresholds."""

    def test_failure_burst(self):
        last_run = mock.Mock(run_state="failed")
        decision = _classify_pipeline_state(
            failed=5,
            completed=0,
            terminal=5,
            success_rate=0,
            hours_since=1.0,
            no_run_threshold=24,
            failure_threshold=20,
            last_run=last_run,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_ERROR)

    def test_no_recent_run(self):
        last_run = mock.Mock(run_state="completed")
        decision = _classify_pipeline_state(
            failed=0,
            completed=2,
            terminal=2,
            success_rate=100,
            hours_since=48.0,
            no_run_threshold=24,
            failure_threshold=20,
            last_run=last_run,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)

    def test_low_success_rate(self):
        last_run = mock.Mock(run_state="completed")
        decision = _classify_pipeline_state(
            failed=2,
            completed=2,
            terminal=4,
            success_rate=50,
            hours_since=1.0,
            no_run_threshold=24,
            failure_threshold=20,
            last_run=last_run,
        )
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)

    def test_healthy_returns_none(self):
        last_run = mock.Mock(run_state="completed")
        decision = _classify_pipeline_state(
            failed=0,
            completed=10,
            terminal=10,
            success_rate=100,
            hours_since=1.0,
            no_run_threshold=24,
            failure_threshold=20,
            last_run=last_run,
        )
        self.assertIsNone(decision)


class ClassifyCrawlerSessionStateTests(SimpleTestCase):
    """Verify crawler-session wording for the three statuses."""

    def test_failed_session(self):
        latest = mock.Mock(
            status="failed",
            site_domain="x.com",
            error_message="boom",
            pages_crawled=10,
        )
        decision = _classify_crawler_session_state(latest)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_WARNING)
        self.assertIn("failed", decision["label"])

    def test_running_session(self):
        latest = mock.Mock(status="running", pages_crawled=42, site_domain="x.com")
        decision = _classify_crawler_session_state(latest)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)
        self.assertIn("42", decision["label"])

    def test_completed_session(self):
        latest = mock.Mock(status="completed", pages_crawled=100, site_domain="x.com")
        decision = _classify_crawler_session_state(latest)
        self.assertEqual(decision["status"], ServiceHealthRecord.STATUS_HEALTHY)





class SearchMetricCheckConfigTests(SimpleTestCase):
    """Verify the GA4/GSC config dataclass + freshness helper."""

    def test_dataclass_construction(self):
        cfg = _SearchMetricCheckConfig(
            service_key="test",
            setting_key="x",
            source="t",
            not_configured_label="nc",
            not_configured_issue="ni",
            not_configured_fix="nf",
            stale_threshold_setting="t_thresh",
            stale_label="sl",
            stale_issue_template="lag {lag_hours}h",
            stale_fix="sf",
            empty_label="el",
            empty_issue="ei",
            empty_fix="ef",
            healthy_label="hl",
            healthy_issue="hi",
            error_label="erl",
            error_fix="erf",
        )
        self.assertEqual(cfg.service_key, "test")
        self.assertIsNone(cfg.enrich_metadata)
        self.assertIsNone(cfg.extra_metadata_provider)

    def test_freshness_helper_returns_none_when_no_metric(self):
        cfg = _SearchMetricCheckConfig(
            service_key="test",
            setting_key="x",
            source="t",
            not_configured_label="",
            not_configured_issue="",
            not_configured_fix="",
            stale_threshold_setting="t",
            stale_label="",
            stale_issue_template="",
            stale_fix="",
            empty_label="",
            empty_issue="",
            empty_fix="",
            healthy_label="",
            healthy_issue="",
            error_label="",
            error_fix="",
        )
        self.assertIsNone(_check_metric_freshness(cfg, None, {}))
