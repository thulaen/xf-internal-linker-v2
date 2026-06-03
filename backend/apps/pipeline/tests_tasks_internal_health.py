from unittest import mock
from django.test import SimpleTestCase

class TestTasksInternalHealth(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_internal_health.connection")
    @mock.patch("apps.pipeline.services.disk_pressure.refresh_disk_pressure_state")
    def test_refresh_disk_pressure_state_guard(self, mock_refresh, mock_connection):
        mock_connection.in_atomic_block = False
        mock_refresh.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_internal_health import refresh_disk_pressure_state
        with self.assertRaises(Exception) as ctx:
            refresh_disk_pressure_state()
        
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.pipeline.tasks_internal_health.connection")
    @mock.patch("apps.pipeline.services.pipeline_stages.get_stage2_path_runtime_status")
    def test_cpp_fallback_share_check_guard(self, mock_get, mock_connection):
        mock_connection.in_atomic_block = False
        mock_get.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_internal_health import cpp_fallback_share_check
        with self.assertRaises(Exception) as ctx:
            cpp_fallback_share_check()
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.pipeline.tasks_internal_health.connection")
    @mock.patch("apps.pipeline.services.pipeline_stages.get_stage2_path_runtime_status")
    @mock.patch("apps.auto_issues.services.dedup.upsert_dedup")
    def test_cpp_fallback_share_check_alert(self, mock_upsert, mock_get, mock_connection):
        mock_connection.in_atomic_block = True
        mock_get.return_value = {"python_share": 0.1, "alert_threshold": 0.05}
        
        from apps.pipeline.tasks_internal_health import cpp_fallback_share_check
        res = cpp_fallback_share_check()
        
        self.assertEqual(res["share"], 0.1)
        self.assertEqual(res["threshold"], 0.05)
        self.assertEqual(res["alert"], True)
        mock_upsert.assert_called_once()
