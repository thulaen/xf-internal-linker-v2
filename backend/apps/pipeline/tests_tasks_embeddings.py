from unittest import mock
from django.test import SimpleTestCase

class TestTasksEmbeddings(SimpleTestCase):
    @mock.patch("apps.pipeline.tasks_embeddings.connection")
    @mock.patch("apps.pipeline.services.faiss_index.build_faiss_index")
    def test_refresh_faiss_index_guard(self, mock_build, mock_connection):
        mock_connection.in_atomic_block = False
        mock_build.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_embeddings import refresh_faiss_index
        with self.assertRaises(Exception) as ctx:
            refresh_faiss_index()
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()

    @mock.patch("apps.pipeline.tasks_embeddings.connection")
    @mock.patch("apps.pipeline.services.nrt_delta_index.flush_delta_index")
    def test_nrt_delta_flush_guard(self, mock_flush, mock_connection):
        mock_connection.in_atomic_block = False
        mock_flush.side_effect = Exception("Sentinel")
        
        from apps.pipeline.tasks_embeddings import nrt_delta_flush
        with self.assertRaises(Exception) as ctx:
            nrt_delta_flush()
            
        self.assertEqual(str(ctx.exception), "Sentinel")
        mock_connection.close.assert_called_once()
