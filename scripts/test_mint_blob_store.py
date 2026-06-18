"""Tests for the Mint shard storage reader."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from mint_blob_store import MintBlobStore


class TestMintBlobStore(TestCase):
    def test_read_manifest_returns_json_lines(self) -> None:
        store = MintBlobStore("mint", "xf", "/srv/xf")
        completed = type("Completed", (), {"returncode": 0, "stdout": '{"a": 1}\n'})
        with patch.object(store, "_ssh", return_value=completed):
            self.assertEqual(store.read_manifest("run-1"), [{"a": 1}])

    def test_blob_exists_uses_sha_prefix(self) -> None:
        store = MintBlobStore("mint", "xf", "/srv/xf")
        completed = type("Completed", (), {"returncode": 0, "stdout": ""})
        with patch.object(store, "_ssh", return_value=completed) as ssh:
            self.assertTrue(store.blob_exists("abcdef"))
        self.assertIn("/ab/abcdef", ssh.call_args.args[0])
