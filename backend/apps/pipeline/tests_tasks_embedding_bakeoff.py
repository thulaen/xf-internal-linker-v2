from unittest import mock
from django.test import SimpleTestCase

class TestTasksEmbeddingBakeoff(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_embedding_bakeoff.connection")
    @mock.patch("apps.core.models.AppSetting.get_int")
    def test_embedding_provider_bakeoff_guard(self, mock_get_int, mock_connection):
        mock_connection.in_atomic_block = False
        mock_get_int.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_embedding_bakeoff import embedding_provider_bakeoff
        
        with self.assertRaises(Exception) as ctx:
            embedding_provider_bakeoff()  # pylint: disable=no-value-for-parameter
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.core.models.AppSetting.get_str")
    def test_discover_providers_with_key(self, mock_get_str):
        mock_get_str.return_value = "dummy_key"
        from apps.pipeline.tasks_embedding_bakeoff import _discover_providers
        providers = _discover_providers()
        self.assertIn("local", providers)
        self.assertIn("openai", providers)
        self.assertIn("gemini", providers)

    @mock.patch("apps.core.models.AppSetting.get_str")
    def test_discover_providers_no_key(self, mock_get_str):
        mock_get_str.return_value = ""
        from apps.pipeline.tasks_embedding_bakeoff import _discover_providers
        providers = _discover_providers()
        self.assertEqual(providers, ["local"])
