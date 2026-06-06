from unittest import mock
from django.test import SimpleTestCase

class TestTasksImport(SimpleTestCase):
    @mock.patch("apps.core.models.AppSetting.get_int")
    def test_get_max_pages_default(self, mock_get_int):
        mock_get_int.return_value = 500
        from apps.pipeline.tasks_import import _get_max_pages  # noqa: PLC0415
        self.assertEqual(_get_max_pages(), 500)
        mock_get_int.assert_called_once_with("import.max_pages", 500)

    @mock.patch("apps.core.models.AppSetting.get_int")
    def test_get_max_pages_clamp(self, mock_get_int):
        mock_get_int.return_value = -5
        from apps.pipeline.tasks_import import _get_max_pages  # noqa: PLC0415
        self.assertEqual(_get_max_pages(), 1)
        
    @mock.patch("apps.sync.services.jsonl_importer.import_from_jsonl")
    @mock.patch("apps.content.models.ScopeItem.objects.get_or_create")
    @mock.patch("apps.pipeline.tasks_import.process_import_item")
    @mock.patch("apps.pipeline.tasks_import._maybe_flush_and_checkpoint")
    def test_import_jsonl_content(self, mock_flush, mock_process, mock_get_or_create, mock_import):
        mock_import.return_value = [{"scope_id": 1, "scope_type": "node"}]
        mock_get_or_create.return_value = (mock.MagicMock(), True)
        mock_process.return_value = (10, None)
        
        from apps.pipeline.tasks_import import import_jsonl_content, ImportState  # noqa: PLC0415
        
        state = ImportState()
        job = mock.MagicMock()
        import_jsonl_content(state, job, "dummy.jsonl")
        
        mock_import.assert_called_once_with("dummy.jsonl")
        mock_get_or_create.assert_called_once()
        mock_process.assert_called_once()
        mock_flush.assert_called_once_with(state, job, interval=50)
        self.assertEqual(state.updated_pks, [10])
        self.assertEqual(state.items_updated, 1)
