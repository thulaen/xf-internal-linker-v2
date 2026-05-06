import numpy as np
from django.test import TestCase

class PassageRelevanceKernelTests(TestCase):
    def test_passagesim_maxsim(self):
        try:
            from extensions import passagesim
        except ImportError:
            self.skipTest("passagesim C++ kernel not built")
            
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array([
            [0.5, 0.5, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        ], dtype=np.float32)
        
        best_sim, best_idx = passagesim.maxsim(q, matrix)
        self.assertEqual(best_idx, 1)
        self.assertAlmostEqual(best_sim, 1.0, places=5)

    def test_quantemb_encode(self):
        try:
            from extensions import quantemb
        except ImportError:
            self.skipTest("quantemb C++ kernel not built")

        # Mock codebooks: 2 subvectors, 4 clusters each, 2 dims per subvector (4 total dims).
        codebooks = np.random.rand(2, 4, 2).astype(np.float32)
        rotation = np.eye(4, dtype=np.float32)  # Identity rotation = no OPQ rotation.
        vectors = np.random.rand(10, 4).astype(np.float32)

        codes = quantemb.opq_encode(vectors, rotation, codebooks)
        self.assertEqual(codes.shape, (10, 2))
        self.assertEqual(codes.dtype, np.uint8)
