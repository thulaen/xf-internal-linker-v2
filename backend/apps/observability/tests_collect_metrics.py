"""collect_system_metrics now emits LIVE gauge/histogram values for the reserved
metrics that have a reliable in-container source (was a stub returning
``{"collected": True}`` and emitting nothing).

These tests mock psutil / Redis / the DB cursor and capture the safe_set /
safe_observe calls, so they prove the emission wiring without touching the real
system.
"""

from unittest import mock

from django.test import SimpleTestCase


class EmitMetricsTests(SimpleTestCase):
    @staticmethod
    def _capture():
        calls: dict[str, tuple] = {}

        def fake(metric, value, **labels):
            calls[metric] = (value, labels)

        return calls, fake

    def test_system_gauges_emitted_from_psutil(self):
        from apps.observability import tasks

        calls, fake_set = self._capture()
        with mock.patch("psutil.Process") as proc, mock.patch("psutil.disk_usage") as disk, mock.patch(
            "apps.observability.api.get_metric", side_effect=lambda name: name
        ), mock.patch("apps.observability.instruments.safe_set", side_effect=fake_set):
            proc.return_value.memory_info.return_value.rss = 123456
            disk.return_value.used = 40
            disk.return_value.total = 100
            out = tasks._emit_system_gauges()

        self.assertEqual(calls["xf_system_memory_rss_bytes"], (123456.0, {"service": "backend"}))
        self.assertEqual(calls["xf_system_disk_usage_bytes"], (40.0, {"mount": "/"}))
        self.assertEqual(calls["xf_system_disk_capacity_bytes"], (100.0, {"mount": "/"}))
        self.assertEqual(out["memory_rss_bytes"], 123456.0)

    def test_queue_depth_emitted_from_redis(self):
        from apps.observability import tasks

        calls, fake_set = self._capture()
        fake_client = mock.MagicMock()
        fake_client.llen.return_value = 7
        with mock.patch("redis.Redis.from_url", return_value=fake_client), mock.patch(
            "apps.observability.api.get_metric", side_effect=lambda name: name
        ), mock.patch("apps.observability.instruments.safe_set", side_effect=fake_set):
            out = tasks._emit_queue_depth()

        # All three Celery queues are probed; the gauge is set once per queue.
        self.assertEqual(out, {"default": 7.0, "pipeline": 7.0, "embeddings": 7.0})
        self.assertEqual(calls["xf_queue_depth"][0], 7.0)

    def test_db_latency_observed(self):
        from apps.observability import tasks

        observed: dict[str, tuple] = {}

        def fake_observe(metric, value, **labels):
            observed[metric] = (value, labels)

        with mock.patch.object(tasks, "connection", mock.MagicMock()), mock.patch(
            "apps.observability.api.get_metric", side_effect=lambda name: name
        ), mock.patch("apps.observability.instruments.safe_observe", side_effect=fake_observe):
            elapsed = tasks._emit_db_latency()

        self.assertIn("xf_db_latency_seconds", observed)
        self.assertEqual(observed["xf_db_latency_seconds"][1], {"operation": "select", "status": "ok"})
        self.assertGreaterEqual(elapsed, 0.0)
