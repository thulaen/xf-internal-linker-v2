from unittest import mock
from django.test import SimpleTestCase
from datetime import datetime, timezone

class TestTasksMonthly(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_monthly.connection")
    @mock.patch("django.core.management.call_command")
    def test_run_monthly_top_50_celery_guard(self, mock_call, mock_connection):
        mock_connection.in_atomic_block = False
        mock_call.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_monthly import run_monthly_top_50_celery
        with self.assertRaises(Exception) as ctx:
            run_monthly_top_50_celery()
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.pipeline.tasks_monthly.connection")
    @mock.patch("django.core.management.call_command")
    def test_run_monthly_top_50_celery_success(self, mock_call, mock_connection):
        mock_connection.in_atomic_block = True
        
        from apps.pipeline.tasks_monthly import run_monthly_top_50_celery
        res = run_monthly_top_50_celery()
        
        expected_month = datetime.now(timezone.utc).strftime("%Y-%m")
        self.assertEqual(res["month"], expected_month)
        self.assertEqual(res["strategy"], "python")
        mock_call.assert_called_once_with("run_monthly_top_50", month=expected_month, strategy="python")
