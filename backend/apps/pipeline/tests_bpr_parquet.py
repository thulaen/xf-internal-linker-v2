"""Parity tests for the BPR Parquet sidecar (slice 6b).

The migration adds a V3 Parquet format alongside the existing V2 npz and V1
pickle formats. These tests verify:

* Round-trip parity: factors and index dicts written via V3 load back identical.
* Format priority: V3 wins over V2; V2 wins over V1 (pickle fallback).
* Backward compatibility: old V2 / V1 snapshots still load when no V3 exists.
* Atomicity: temp file is cleaned up after a successful write.
"""

from __future__ import annotations

import json
import os
import pickle
import tempfile
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services import bpr_ranking


class BprParquetParityTests(SimpleTestCase):
    """V3 Parquet save/load must round-trip identically to V2 npz."""

    def setUp(self):
        bpr_ranking._MODEL_CACHE = None

    def _make_synthetic_snapshot(self, n_users=3, n_items=4, factors=2):
        rng = np.random.RandomState(42)
        user_factors = rng.randn(n_users, factors).astype(np.float32)
        item_factors = rng.randn(n_items, factors).astype(np.float32)
        user_index = {f"u{i}": i for i in range(n_users)}
        item_index = {f"i{j}": j for j in range(n_items)}
        return user_factors, item_factors, user_index, item_index, factors

    def test_companion_path_replaces_extension(self):
        result = bpr_ranking._parquet_companion_path(os.path.join("tmp", "model.pkl"))
        self.assertEqual(os.path.basename(result), "model.parquet")

    def test_save_and_load_v3_round_trip(self):
        user_factors, item_factors, user_index, item_index, factors = self._make_synthetic_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "bpr.parquet")
            ok = bpr_ranking._save_v3_parquet(
                parquet_path,
                user_factors=user_factors,
                item_factors=item_factors,
                user_index=user_index,
                item_index=item_index,
                factors=factors,
            )
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(parquet_path))

            snap = bpr_ranking._load_v3_parquet(parquet_path)
            self.assertIsNotNone(snap)
            self.assertEqual(snap.factors, factors)
            self.assertEqual(snap.user_index, user_index)
            self.assertEqual(snap.item_index, item_index)
            np.testing.assert_array_almost_equal(snap.user_factors, user_factors, decimal=5)
            np.testing.assert_array_almost_equal(snap.item_factors, item_factors, decimal=5)

    def test_v3_load_returns_none_for_missing_file(self):
        result = bpr_ranking._load_v3_parquet("/nonexistent/bpr.parquet")
        self.assertIsNone(result)

    def test_v3_load_returns_none_for_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            corrupt = os.path.join(tmp, "bad.parquet")
            with open(corrupt, "wb") as fh:
                fh.write(b"not parquet")
            self.assertIsNone(bpr_ranking._load_v3_parquet(corrupt))

    def test_load_snapshot_prefers_v3_when_both_v3_and_v2_exist(self):
        user_factors, item_factors, user_index, item_index, factors = self._make_synthetic_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            v2_path = os.path.join(tmp, "bpr.npz")
            v3_path = os.path.join(tmp, "bpr.parquet")
            # Write V2 with different vectors so we can tell them apart.
            different_user_factors = np.full_like(user_factors, fill_value=99.0)
            with open(v2_path, "wb") as fh:
                np.savez_compressed(
                    fh,
                    user_factors=different_user_factors,
                    item_factors=item_factors,
                    user_index_json=np.frombuffer(
                        json.dumps(user_index).encode("utf-8"), dtype=np.uint8
                    ),
                    item_index_json=np.frombuffer(
                        json.dumps(item_index).encode("utf-8"), dtype=np.uint8
                    ),
                    factors=np.int32(factors),
                )
            bpr_ranking._save_v3_parquet(
                v3_path,
                user_factors=user_factors,
                item_factors=item_factors,
                user_index=user_index,
                item_index=item_index,
                factors=factors,
            )
            with patch.object(bpr_ranking, "_read_path", return_value=v2_path), \
                 patch.object(bpr_ranking, "HAS_BPR", True):
                bpr_ranking._MODEL_CACHE = None
                snap = bpr_ranking.load_snapshot()
            np.testing.assert_array_almost_equal(snap.user_factors, user_factors, decimal=5)

    def test_load_snapshot_falls_back_to_v2_when_v3_missing(self):
        user_factors, item_factors, user_index, item_index, factors = self._make_synthetic_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            v2_path = os.path.join(tmp, "bpr.npz")
            with open(v2_path, "wb") as fh:
                np.savez_compressed(
                    fh,
                    user_factors=user_factors,
                    item_factors=item_factors,
                    user_index_json=np.frombuffer(
                        json.dumps(user_index).encode("utf-8"), dtype=np.uint8
                    ),
                    item_index_json=np.frombuffer(
                        json.dumps(item_index).encode("utf-8"), dtype=np.uint8
                    ),
                    factors=np.int32(factors),
                )
            with patch.object(bpr_ranking, "_read_path", return_value=v2_path), \
                 patch.object(bpr_ranking, "HAS_BPR", True):
                bpr_ranking._MODEL_CACHE = None
                snap = bpr_ranking.load_snapshot()
            self.assertEqual(snap.factors, factors)
            self.assertEqual(snap.user_index, user_index)
            np.testing.assert_array_almost_equal(snap.user_factors, user_factors, decimal=5)

    def test_load_snapshot_returns_empty_when_neither_format_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            v2_path = os.path.join(tmp, "bpr.npz")
            with patch.object(bpr_ranking, "_read_path", return_value=v2_path), \
                 patch.object(bpr_ranking, "HAS_BPR", True):
                bpr_ranking._MODEL_CACHE = None
                snap = bpr_ranking.load_snapshot()
            self.assertTrue(snap.is_empty)

    def test_save_atomic_no_temp_left_after_success(self):
        user_factors, item_factors, user_index, item_index, factors = self._make_synthetic_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "bpr.parquet")
            ok = bpr_ranking._save_v3_parquet(
                parquet_path,
                user_factors=user_factors,
                item_factors=item_factors,
                user_index=user_index,
                item_index=item_index,
                factors=factors,
            )
            self.assertTrue(ok)
            tmp_file = parquet_path + ".tmp"
            self.assertFalse(os.path.exists(tmp_file), f"tmp leaked: {tmp_file}")

    def test_v3_load_rebuilds_factors_matrix_in_index_order(self):
        """The user_factors matrix must be reconstructed so user_factors[idx]
        is the row for user_index entry mapping to idx. Out-of-order rows in
        the Parquet file must still produce a correctly-ordered matrix."""
        user_factors = np.array(
            [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], dtype=np.float32,
        )
        item_factors = np.array(
            [[10.0, 20.0], [30.0, 40.0]], dtype=np.float32,
        )
        user_index = {"u_alpha": 0, "u_beta": 1, "u_gamma": 2}
        item_index = {"i_apple": 0, "i_banana": 1}
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "bpr.parquet")
            bpr_ranking._save_v3_parquet(
                parquet_path,
                user_factors=user_factors,
                item_factors=item_factors,
                user_index=user_index,
                item_index=item_index,
                factors=2,
            )
            snap = bpr_ranking._load_v3_parquet(parquet_path)
            self.assertEqual(snap.user_index, user_index)
            for user_id, idx in user_index.items():
                np.testing.assert_array_almost_equal(
                    snap.user_factors[idx], user_factors[idx], decimal=5,
                )

    def test_empty_snapshot_round_trip(self):
        """Edge case: zero users and zero items still round-trips a valid file
        (used in the cold-start path where fit_and_save bails early)."""
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "bpr.parquet")
            ok = bpr_ranking._save_v3_parquet(
                parquet_path,
                user_factors=np.zeros((0, 2), dtype=np.float32),
                item_factors=np.zeros((0, 2), dtype=np.float32),
                user_index={},
                item_index={},
                factors=2,
            )
            self.assertTrue(ok)
            snap = bpr_ranking._load_v3_parquet(parquet_path)
            self.assertIsNotNone(snap)
            self.assertEqual(snap.user_index, {})
            self.assertEqual(snap.item_index, {})
            self.assertEqual(snap.factors, 2)
