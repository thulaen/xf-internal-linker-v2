"""
Tests for scripts/shard_manifest.py

BDD:
  Given a desired shard count N and a compute profile
  When distribute_shards() is called
  Then the returned integers sum exactly to N
  And the distribution reflects the declared weight percentages

Tiny shard counts (N=1..10) are parametrized to protect against
off-by-one errors in the remainder distribution loop.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase

# Import shard_manifest from scripts/ without requiring it to be a package.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "shard_manifest.py"


def _load_shard_manifest():
    spec = importlib.util.spec_from_file_location("shard_manifest", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Cached at import time so tests share a single load.
try:
    sm = _load_shard_manifest()
except FileNotFoundError:
    sm = None  # Red phase: module doesn't exist yet


class TestModuleExists(TestCase):
    def test_shard_manifest_module_importable(self) -> None:
        self.assertIsNotNone(sm, "shard_manifest.py must exist under scripts/")

    def test_storage_placement_is_mint(self) -> None:
        self.assertEqual(sm.STORAGE_PLACEMENT, "mint",
                         "STORAGE_PLACEMENT must be 'mint' — durable outputs go to Mint")

    def test_profiles_keys(self) -> None:
        self.assertIn("2m", sm.PROFILES)
        self.assertIn("3m_one_strong", sm.PROFILES)
        self.assertIn("3m_two_strong", sm.PROFILES)


class TestDistributeShards(TestCase):
    """Unit tests for distribute_shards() — pure function, no I/O."""

    def _check_total(self, n: int, weights: list[int]) -> None:
        result = sm.distribute_shards(n, weights)
        self.assertEqual(sum(result), n,
                         f"distribute_shards({n}, {weights}) summed to {sum(result)}, expected {n}")
        self.assertEqual(len(result), len(weights))

    def test_2m_100_shards(self) -> None:
        result = sm.distribute_shards(100, [65, 35])
        self.assertEqual(result[0], 65, "Windows must get 65 of 100 shards")
        self.assertEqual(result[1], 35, "Mint must get 35 of 100 shards")

    def test_2m_20_shards(self) -> None:
        result = sm.distribute_shards(20, [65, 35])
        self.assertEqual(result[0], 13, "Windows must get 13 of 20 shards")
        self.assertEqual(result[1], 7, "Mint must get 7 of 20 shards")
        self.assertEqual(sum(result), 20)

    def test_2m_1_shard_total_is_1(self) -> None:
        result = sm.distribute_shards(1, [65, 35])
        self.assertEqual(sum(result), 1)
        self.assertGreaterEqual(result[0], 0)
        self.assertGreaterEqual(result[1], 0)

    def test_2m_0_shards(self) -> None:
        result = sm.distribute_shards(0, [65, 35])
        self.assertEqual(result, [0, 0])

    def test_3m_one_strong_120_shards_total(self) -> None:
        result = sm.distribute_shards(120, [58, 31, 31])
        self.assertEqual(sum(result), 120)
        # strong node should get approximately 58 (48.3%)
        self.assertAlmostEqual(result[0], 120 * 58 / 120, delta=1)
        # each weak node approximately 31
        self.assertAlmostEqual(result[1], 120 * 31 / 120, delta=1)
        self.assertAlmostEqual(result[2], 120 * 31 / 120, delta=1)

    def test_3m_two_strong_120_shards_total(self) -> None:
        result = sm.distribute_shards(120, [49, 49, 22])
        self.assertEqual(sum(result), 120)
        # two strong nodes approximately 49 each
        self.assertAlmostEqual(result[0], 49, delta=1)
        self.assertAlmostEqual(result[1], 49, delta=1)
        # weak node approximately 22
        self.assertAlmostEqual(result[2], 22, delta=1)

    def test_tiny_shards_2m(self) -> None:
        for n in range(1, 11):
            with self.subTest(n=n):
                self._check_total(n, [65, 35])

    def test_tiny_shards_3m_one_strong(self) -> None:
        for n in range(1, 11):
            with self.subTest(n=n):
                self._check_total(n, [58, 31, 31])

    def test_tiny_shards_3m_two_strong(self) -> None:
        for n in range(1, 11):
            with self.subTest(n=n):
                self._check_total(n, [49, 49, 22])

    def test_equal_weights(self) -> None:
        result = sm.distribute_shards(9, [1, 1, 1])
        self.assertEqual(sum(result), 9)
        self.assertEqual(result, [3, 3, 3])

    def test_single_node(self) -> None:
        result = sm.distribute_shards(7, [1])
        self.assertEqual(result, [7])

    def test_raises_negative_shards(self) -> None:
        with self.assertRaises(ValueError):
            sm.distribute_shards(-1, [65, 35])

    def test_raises_empty_weights(self) -> None:
        with self.assertRaises(ValueError):
            sm.distribute_shards(10, [])

    def test_raises_zero_weight_sum(self) -> None:
        with self.assertRaises(ValueError):
            sm.distribute_shards(10, [0, 0])


class TestGenerateManifest(TestCase):
    """Integration tests for generate_manifest() — calls distribute_shards()."""

    def test_2m_manifest_100(self) -> None:
        m = sm.generate_manifest("2m", 100)
        self.assertEqual(m.total(), 100)
        self.assertEqual(m.allocation["windows"], 65)
        self.assertEqual(m.allocation["mint"], 35)
        self.assertEqual(m.profile, "2m")
        self.assertEqual(m.n_shards, 100)

    def test_2m_manifest_20(self) -> None:
        m = sm.generate_manifest("2m", 20)
        self.assertEqual(m.total(), 20)
        self.assertEqual(m.allocation["windows"], 13)
        self.assertEqual(m.allocation["mint"], 7)

    def test_3m_one_strong_manifest_120(self) -> None:
        m = sm.generate_manifest("3m_one_strong", 120)
        self.assertEqual(m.total(), 120)
        self.assertIn("strong", m.allocation)
        self.assertIn("weak1", m.allocation)
        self.assertIn("weak2", m.allocation)

    def test_3m_two_strong_manifest_120(self) -> None:
        m = sm.generate_manifest("3m_two_strong", 120)
        self.assertEqual(m.total(), 120)
        self.assertIn("strong1", m.allocation)
        self.assertIn("strong2", m.allocation)
        self.assertIn("weak", m.allocation)

    def test_unknown_profile_raises(self) -> None:
        with self.assertRaises(KeyError):
            sm.generate_manifest("unknown_profile", 100)

    def test_manifest_total_method(self) -> None:
        m = sm.generate_manifest("2m", 50)
        self.assertEqual(m.total(), 50)
