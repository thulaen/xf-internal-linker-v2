from unittest import mock
from django.test import SimpleTestCase

class TestTasksEmbeddingAudit(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_embedding_audit.connection")
    @mock.patch("apps.pipeline.services.embedding_audit.is_audit_enabled")
    def test_embedding_accuracy_audit_guard(self, mock_is_enabled, mock_connection):
        mock_connection.in_atomic_block = False
        mock_is_enabled.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_embedding_audit import embedding_accuracy_audit
        
        with self.assertRaises(Exception) as ctx:
            embedding_accuracy_audit(fortnightly=True, force=False)  # pylint: disable=no-value-for-parameter
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.pipeline.tasks_embedding_audit.connection")
    @mock.patch("apps.pipeline.services.embedding_audit.is_audit_enabled")
    def test_embedding_accuracy_audit_skipped(self, mock_is_enabled, mock_connection):
        mock_connection.in_atomic_block = True
        mock_is_enabled.return_value = False
        
        from apps.pipeline.tasks_embedding_audit import embedding_accuracy_audit
        
        res = embedding_accuracy_audit(fortnightly=True, force=False)  # pylint: disable=no-value-for-parameter
        self.assertEqual(res, {"skipped": "disabled"})
