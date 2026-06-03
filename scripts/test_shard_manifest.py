import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "shard_manifest.py"
_spec = importlib.util.spec_from_file_location("shard_manifest", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class ShardManifestTests(unittest.TestCase):
    def test_distribute_shards_exact(self):
        weights = [50, 50]
        self.assertEqual(mod.distribute_shards(10, weights), [5, 5])

    def test_distribute_shards_largest_remainder(self):
        # weights = [65, 35], n=10. Exact = 6.5, 3.5. Floors = 6, 3. Remainder = 1.
        # fractional parts: 0.5, 0.5. They are equal. Sorted uses original order, so first gets +1.
        # Result: [7, 3]
        weights = [65, 35]
        self.assertEqual(mod.distribute_shards(10, weights), [7, 3])

    def test_distribute_shards_three_nodes(self):
        weights = [58, 31, 31] # sum 120
        # n = 5
        # Exact: 2.41, 1.29, 1.29
        # Floors: 2, 1, 1 -> sum 4, remainder 1
        # Fractionals: 0.41, 0.29, 0.29
        # First node gets +1. Result: 3, 1, 1
        self.assertEqual(mod.distribute_shards(5, weights), [3, 1, 1])

    def test_distribute_shards_zero_shards(self):
        self.assertEqual(mod.distribute_shards(0, [65, 35]), [0, 0])

    def test_generate_manifest(self):
        manifest = mod.generate_manifest("2m", 10)
        self.assertEqual(manifest.profile, "2m")
        self.assertEqual(manifest.n_shards, 10)
        self.assertEqual(manifest.allocation["windows"], 7)
        self.assertEqual(manifest.allocation["mint"], 3)
        self.assertEqual(manifest.total(), 10)

if __name__ == "__main__":
    unittest.main()
