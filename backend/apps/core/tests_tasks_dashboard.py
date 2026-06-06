from unittest.mock import patch
from django.test import SimpleTestCase
from apps.core.tasks_dashboard import refresh_dashboard_matviews

class TestRefreshDashboardMatviews(SimpleTestCase):
    @patch("apps.core.tasks_dashboard.connection")
    def test_when_not_in_atomic_block_then_connection_closed(self, mock_connection):
        mock_connection.in_atomic_block = False
        
        with patch("apps.core.services.dashboard_aggregates.refresh_suggestion_counts_matview") as mock_refresh:
            mock_refresh.side_effect = Exception("Stop early")
            
            with self.assertRaisesMessage(Exception, "Stop early"):
                refresh_dashboard_matviews()
                
            mock_connection.close.assert_called_once()

    @patch("apps.core.tasks_dashboard.connection")
    @patch("apps.core.services.dashboard_aggregates.refresh_suggestion_counts_matview")
    def test_when_refresh_succeeds_then_returns_dict(self, mock_refresh, mock_connection):
        mock_connection.in_atomic_block = True
        mock_refresh.return_value = True
        
        result = refresh_dashboard_matviews()
        
        self.assertEqual(result, {"dashboard_suggestion_counts_mv": True})
        mock_refresh.assert_called_once_with(concurrently=True)
