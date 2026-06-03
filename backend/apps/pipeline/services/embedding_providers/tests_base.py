from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
import numpy as np
from apps.pipeline.services.embedding_providers.base import (
    compute_signature,
    default_should_pause,
    l2_normalise_inplace,
    mean_pool_chunks,
)

class _StopAfterGuard(Exception): pass

class EmbeddingProviderBaseTests(SimpleTestCase):
    def test_compute_signature(self):
        sig = compute_signature("openai", "text-embedding-3-small", 1536)
        self.assertEqual(sig, "openai:text-embedding-3-small:1536")

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_default_should_pause_true(self, mock_filter):
        mock_qs = MagicMock()
        mock_filter.return_value = mock_qs
        mock_qs.first.return_value.value = "true"
        self.assertEqual(default_should_pause(), "system_master_pause")

    @patch('apps.core.models.AppSetting.objects.filter')
    def test_default_should_pause_false(self, mock_filter):
        mock_qs = MagicMock()
        mock_filter.return_value = mock_qs
        mock_qs.first.return_value.value = "false"
        self.assertIsNone(default_should_pause())

    @patch('apps.core.models.AppSetting.objects.filter', side_effect=Exception)
    def test_default_should_pause_exception(self, mock_filter):
        self.assertIsNone(default_should_pause())

    def test_l2_normalise_inplace_empty(self):
        mat = np.array([[]])
        res = l2_normalise_inplace(mat)
        self.assertEqual(res.size, 0)

    def test_l2_normalise_inplace_already_norm(self):
        mat = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        res = l2_normalise_inplace(mat)
        self.assertTrue(np.allclose(res, [[1.0, 0.0], [0.0, 1.0]]))

    def test_l2_normalise_inplace_unnorm(self):
        mat = np.array([[2.0, 0.0], [0.0, 3.0]], dtype=np.float32)
        res = l2_normalise_inplace(mat)
        self.assertTrue(np.allclose(res, [[1.0, 0.0], [0.0, 1.0]]))

    def test_mean_pool_chunks_invalid_ndim(self):
        with self.assertRaisesMessage(ValueError, "chunk_vectors must be 2-D (n_chunks, dim)"):
            mean_pool_chunks(np.array([1, 2, 3]))

    def test_mean_pool_chunks_valid(self):
        chunks = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
        res = mean_pool_chunks(chunks)
        expected_norm = np.linalg.norm([2.0/3.0, 1.0/3.0])
        expected_0 = (2.0/3.0) / expected_norm
        expected_1 = (1.0/3.0) / expected_norm
        self.assertTrue(np.allclose(res, [expected_0, expected_1]))
