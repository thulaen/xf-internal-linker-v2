from unittest import mock
from django.test import SimpleTestCase

class TestTasksLinkHealth(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_link_health.connection")
    @mock.patch("apps.suggestions.models.Suggestion.objects.filter")
    def test_verify_suggestions_guard(self, mock_filter, mock_connection):
        mock_connection.in_atomic_block = False
        mock_filter.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_link_health import verify_suggestions
        
        with self.assertRaises(Exception) as ctx:
            verify_suggestions(suggestion_ids=["foo"])
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()
