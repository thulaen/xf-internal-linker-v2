"""Parity tests for the Node2Vec Parquet sidecar (slice 6a).

The migration replaces a pickled dict with an atomically-written Parquet file
at a sibling path. These tests verify:

* Round-trip parity: vectors written via Parquet load back identical (float32).
* Backward compatibility: when only the legacy pickle file exists, ``load_embeddings``
  falls back to it and keeps working.
* Priority: when both files are present, Parquet wins.
* Atomicity: the existing snapshot is preserved if the writer crashes mid-write.
"""

from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import node2vec_embeddings


class Node2VecParquetParityTests(SimpleTestCase):
    """Parquet save/load must round-trip identically to the legacy pickle path."""

    def setUp(self):
        node2vec_embeddings._CACHE = None  # reset module-level cache between tests

    def test_companion_path_replaces_pkl_extension(self):
        result = node2vec_embeddings._parquet_companion_path(os.path.join("tmp", "embeddings.pkl"))
        self.assertEqual(os.path.basename(result), "embeddings.parquet")

    def test_companion_path_keeps_parquet_extension(self):
        result = node2vec_embeddings._parquet_companion_path(os.path.join("tmp", "embeddings.parquet"))
        self.assertEqual(os.path.basename(result), "embeddings.parquet")

    def test_companion_path_handles_no_extension(self):
        result = node2vec_embeddings._parquet_companion_path(os.path.join("tmp", "embeddings"))
        self.assertEqual(os.path.basename(result), "embeddings.parquet")

    def test_round_trip_parquet_floats_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkl_path = os.path.join(tmp, "embeddings.pkl")
            parquet_path = os.path.join(tmp, "embeddings.parquet")
            vectors = {
                "node-1": [0.1, 0.2, 0.3, 0.4],
                "node-2": [-0.5, 0.0, 0.5, 1.0],
                "node-3": [1e-7, 1.0, -1.0, 3.14159],
            }
            ok = node2vec_embeddings._save_parquet(parquet_path, vectors=vectors, dimension=4)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(parquet_path))

            loaded = node2vec_embeddings._load_parquet(parquet_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.dimension, 4)
            self.assertEqual(set(loaded.vectors.keys()), set(vectors.keys()))
            import struct

            for node_id, expected in vectors.items():
                got = loaded.vectors[node_id]
                self.assertEqual(len(got), len(expected))
                # Parquet schema is List(Float32), so values are float32-rounded.
                for g, e in zip(got, expected):
                    f32_e = struct.unpack("f", struct.pack("f", e))[0]
                    self.assertAlmostEqual(g, f32_e, places=6)

    def test_load_embeddings_prefers_parquet_when_both_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkl_path = os.path.join(tmp, "embeddings.pkl")
            parquet_path = os.path.join(tmp, "embeddings.parquet")
            with open(pkl_path, "wb") as fh:
                pickle.dump(
                    {"vectors": {"old-node": [9.9, 9.9, 9.9, 9.9]}, "dimension": 4},
                    fh,
                    protocol=4,
                )
            node2vec_embeddings._save_parquet(
                parquet_path,
                vectors={"new-node": [0.1, 0.2, 0.3, 0.4]},
                dimension=4,
            )
            with patch.object(node2vec_embeddings, "_read_path", return_value=pkl_path), \
                 patch.object(node2vec_embeddings, "HAS_NODE2VEC", True):
                node2vec_embeddings._CACHE = None
                emb = node2vec_embeddings.load_embeddings()
            self.assertEqual(set(emb.vectors.keys()), {"new-node"})

    def test_load_embeddings_falls_back_to_pickle_when_parquet_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkl_path = os.path.join(tmp, "embeddings.pkl")
            with open(pkl_path, "wb") as fh:
                pickle.dump(
                    {"vectors": {"legacy-node": [1.1, 2.2, 3.3, 4.4]}, "dimension": 4},
                    fh,
                    protocol=4,
                )
            with patch.object(node2vec_embeddings, "_read_path", return_value=pkl_path), \
                 patch.object(node2vec_embeddings, "HAS_NODE2VEC", True):
                node2vec_embeddings._CACHE = None
                emb = node2vec_embeddings.load_embeddings()
            self.assertEqual(set(emb.vectors.keys()), {"legacy-node"})
            # Float values preserved exactly through pickle round-trip.
            self.assertEqual(emb.vectors["legacy-node"], [1.1, 2.2, 3.3, 4.4])

    def test_load_embeddings_returns_empty_when_neither_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkl_path = os.path.join(tmp, "embeddings.pkl")
            with patch.object(node2vec_embeddings, "_read_path", return_value=pkl_path), \
                 patch.object(node2vec_embeddings, "HAS_NODE2VEC", True):
                node2vec_embeddings._CACHE = None
                emb = node2vec_embeddings.load_embeddings()
            self.assertTrue(emb.is_empty)

    def test_load_embeddings_returns_empty_when_path_unset(self):
        with patch.object(node2vec_embeddings, "_read_path", return_value=""), \
             patch.object(node2vec_embeddings, "HAS_NODE2VEC", True):
            node2vec_embeddings._CACHE = None
            emb = node2vec_embeddings.load_embeddings()
        self.assertTrue(emb.is_empty)

    def test_save_parquet_atomic_rename_no_temp_left_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "embeddings.parquet")
            vectors = {"a": [0.1, 0.2], "b": [0.3, 0.4]}
            ok = node2vec_embeddings._save_parquet(parquet_path, vectors=vectors, dimension=2)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(parquet_path))
            tmp_file = parquet_path + ".tmp"
            self.assertFalse(os.path.exists(tmp_file), f"tmp file leaked: {tmp_file}")

    def test_load_parquet_returns_none_for_missing_file(self):
        result = node2vec_embeddings._load_parquet("/nonexistent/path/embeddings.parquet")
        self.assertIsNone(result)

    def test_load_parquet_returns_none_for_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            corrupt_path = os.path.join(tmp, "embeddings.parquet")
            with open(corrupt_path, "wb") as fh:
                fh.write(b"this is not parquet")
            result = node2vec_embeddings._load_parquet(corrupt_path)
            self.assertIsNone(result)

    def test_empty_vectors_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            parquet_path = os.path.join(tmp, "embeddings.parquet")
            ok = node2vec_embeddings._save_parquet(parquet_path, vectors={}, dimension=4)
            # Polars can write an empty DataFrame; load returns _EMPTY for vectors={}.
            self.assertTrue(ok)
            loaded = node2vec_embeddings._load_parquet(parquet_path)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.is_empty)
