"""
Tests for scripts/mint_blob_store.py, scripts/merge_shard_outputs.py,
and scripts/mint_gc.py

BDD:
  Given a MintBlobStore backed by a fake transport
  When upload() is called with new content
  Then the blob is written via temp-upload and atomically renamed into blob-store
  And a manifest entry with all 10 required fields is appended

  Given upload() is called twice with identical bytes
  When the transport reports blob_exists=True on the second call
  Then the SCP and atomic-rename are NOT called again
  And a second manifest entry IS appended (two references to one blob)

  Given merge-shard logic reads a manifest with required_for_merge=True entries
  When a required blob is absent from the blob store
  Then check_manifests() returns a non-empty error list

  Given mint_gc logic holds manifest references
  When collect_garbage() runs
  Then blobs still referenced by retained manifests are NOT in the delete list
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # register so relative dataclass refs work
    spec.loader.exec_module(mod)
    return mod


try:
    mbs = _load("mint_blob_store", "mint_blob_store.py")
except FileNotFoundError:
    mbs = None

try:
    mso = _load("merge_shard_outputs", "merge_shard_outputs.py")
except FileNotFoundError:
    mso = None

try:
    mgc = _load("mint_gc", "mint_gc.py")
except FileNotFoundError:
    mgc = None


# ---------------------------------------------------------------------------
# Fake transport for unit testing without SSH
# ---------------------------------------------------------------------------

class _FakeTransport:
    """Records calls and simulates Mint SSH/SCP behaviour."""

    def __init__(self, *, existing_blobs: set[str] | None = None,
                 fail_upload: bool = False, fail_move: bool = False):
        self._existing_blobs: set[str] = set(existing_blobs or [])
        self._fail_upload = fail_upload
        self._fail_move = fail_move
        self.upload_calls: list[tuple[str, str]] = []     # (local_path, remote_path)
        self.move_calls: list[tuple[str, str]] = []       # (src, dst)
        self.append_calls: list[tuple[str, str]] = []     # (remote_path, line)
        self._lines: dict[str, list[str]] = {}            # remote_path → lines

    def blob_exists(self, blob_path: str) -> bool:
        return blob_path in self._existing_blobs

    def upload_file(self, local_path: str, remote_path: str) -> None:
        if self._fail_upload:
            raise RuntimeError("SCP failure (simulated)")
        self.upload_calls.append((local_path, remote_path))
        # Simulate the file landing in temp-upload.
        self._existing_blobs.add(remote_path)

    def atomic_move(self, src: str, dst: str) -> None:
        if self._fail_move:
            raise RuntimeError("SSH mv failure (simulated)")
        self.move_calls.append((src, dst))
        self._existing_blobs.discard(src)
        self._existing_blobs.add(dst)

    def append_line(self, remote_path: str, line: str) -> None:
        self.append_calls.append((remote_path, line))
        self._lines.setdefault(remote_path, []).append(line)

    def read_lines(self, remote_path: str) -> list[str]:
        return list(self._lines.get(remote_path, []))

    def list_blobs(self, blob_store_root: str) -> list[str]:
        return [p for p in self._existing_blobs
                if p.startswith(blob_store_root)]

    def delete_blob(self, blob_path: str) -> None:
        self._existing_blobs.discard(blob_path)


def _make_tmp_file(content: bytes = b"hello shard") -> str:
    """Write bytes to a temp file; caller is responsible for cleanup."""
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tf.write(content)
    tf.close()
    return tf.name


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# TestComputeSha256
# ---------------------------------------------------------------------------

class TestComputeSha256(TestCase):

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")

    def test_sha256_of_known_content(self):
        content = b"hello shard"
        path = _make_tmp_file(content)
        try:
            result = mbs.compute_sha256(path)
        finally:
            os.unlink(path)
        self.assertEqual(result, _sha256(content))

    def test_sha256_returns_hex_string(self):
        path = _make_tmp_file(b"x")
        try:
            result = mbs.compute_sha256(path)
        finally:
            os.unlink(path)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)
        int(result, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# TestBlobExists
# ---------------------------------------------------------------------------

class TestBlobExists(TestCase):

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")

    def test_returns_true_when_blob_present(self):
        sha = _sha256(b"present")
        transport = _FakeTransport()
        store = mbs.MintBlobStore("mint", "user", transport=transport)
        transport._existing_blobs.add(store.blob_path(sha))
        self.assertTrue(store.blob_exists(sha))

    def test_returns_false_when_blob_absent(self):
        sha = _sha256(b"absent")
        transport = _FakeTransport()
        store = mbs.MintBlobStore("mint", "user", transport=transport)
        self.assertFalse(store.blob_exists(sha))


# ---------------------------------------------------------------------------
# TestBlobPaths
# ---------------------------------------------------------------------------

class TestBlobPaths(TestCase):

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")

    def test_blob_path_uses_first_two_chars_as_subdir(self):
        store = mbs.MintBlobStore("mint", "user")
        sha = "abcdef1234" + "0" * 54
        path = store.blob_path(sha)
        self.assertIn("/ab/", path)
        self.assertTrue(path.endswith(sha))

    def test_temp_path_in_temp_upload_with_tmp_suffix(self):
        store = mbs.MintBlobStore("mint", "user")
        sha = "abcdef" + "0" * 58
        path = store.temp_path(sha)
        self.assertIn("temp-upload", path)
        self.assertTrue(path.endswith(f"{sha}.tmp"))

    def test_manifest_path_contains_run_id(self):
        store = mbs.MintBlobStore("mint", "user")
        path = store.manifest_path("run-2026-123")
        self.assertIn("run-2026-123", path)
        self.assertTrue(path.endswith("manifest.json"))


# ---------------------------------------------------------------------------
# TestUploadNewBlob
# ---------------------------------------------------------------------------

class TestUploadNewBlob(TestCase):

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")
        self.content = b"new artifact"
        self.local = _make_tmp_file(self.content)
        self.sha = _sha256(self.content)
        self.transport = _FakeTransport()
        self.store = mbs.MintBlobStore("mint-host", "xf-user", transport=self.transport)

    def tearDown(self):
        os.unlink(self.local)

    def _upload(self):
        return self.store.upload(
            self.local,
            run_id="run-001",
            shard_id="shard-0",
            tool="mutmut",
            logical_path="mutation/results.json",
        )

    def test_scp_called_once_for_new_blob(self):
        self._upload()
        self.assertEqual(len(self.transport.upload_calls), 1)

    def test_scp_targets_temp_upload_path(self):
        self._upload()
        _, remote = self.transport.upload_calls[0]
        self.assertIn("temp-upload", remote)
        self.assertIn(self.sha, remote)

    def test_atomic_move_called_to_blob_store(self):
        self._upload()
        self.assertEqual(len(self.transport.move_calls), 1)
        src, dst = self.transport.move_calls[0]
        self.assertIn("temp-upload", src)
        self.assertIn(self.sha[:2], dst)
        self.assertIn(self.sha, dst)

    def test_blob_exists_in_store_after_upload(self):
        self._upload()
        blob_path = self.store.blob_path(self.sha)
        self.assertIn(blob_path, self.transport._existing_blobs)

    def test_temp_upload_not_in_store_after_atomic_move(self):
        self._upload()
        tmp_path = self.store.temp_path(self.sha)
        self.assertNotIn(tmp_path, self.transport._existing_blobs)

    def test_manifest_entry_appended(self):
        self._upload()
        self.assertEqual(len(self.transport.append_calls), 1)

    def test_manifest_entry_has_all_required_fields(self):
        entry = self._upload()
        for field in ("run_id", "worker", "shard_id", "tool", "logical_path",
                      "sha256", "size_bytes", "media_type", "created_at",
                      "required_for_merge"):
            with self.subTest(field=field):
                self.assertIn(field, entry,
                              f"Manifest entry missing required field: {field}")

    def test_manifest_entry_sha256_matches(self):
        entry = self._upload()
        self.assertEqual(entry["sha256"], self.sha)

    def test_manifest_entry_run_id_matches(self):
        entry = self._upload()
        self.assertEqual(entry["run_id"], "run-001")

    def test_manifest_entry_worker_defaults_to_windows(self):
        entry = self._upload()
        self.assertEqual(entry["worker"], "windows")

    def test_manifest_entry_required_for_merge_true_by_default(self):
        entry = self._upload()
        self.assertTrue(entry["required_for_merge"])


# ---------------------------------------------------------------------------
# TestDuplicateUpload
# ---------------------------------------------------------------------------

class TestDuplicateUpload(TestCase):
    """Second upload of identical bytes: one blob, two manifest entries."""

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")
        self.content = b"shared artifact bytes"
        self.local = _make_tmp_file(self.content)
        self.sha = _sha256(self.content)
        self.transport = _FakeTransport()
        self.store = mbs.MintBlobStore("mint-host", "xf-user", transport=self.transport)

    def tearDown(self):
        os.unlink(self.local)

    def test_second_upload_skips_scp(self):
        self.store.upload(self.local, run_id="run-001", shard_id="s0",
                          tool="mutmut", logical_path="p/a.json")
        # Simulate the blob now existing (it does after first upload)
        scp_calls_after_first = len(self.transport.upload_calls)
        self.store.upload(self.local, run_id="run-001", shard_id="s1",
                          tool="mutmut", logical_path="p/b.json")
        self.assertEqual(len(self.transport.upload_calls), scp_calls_after_first,
                         "SCP must NOT be called again for duplicate blob")

    def test_second_upload_skips_atomic_move(self):
        self.store.upload(self.local, run_id="run-001", shard_id="s0",
                          tool="mutmut", logical_path="p/a.json")
        move_calls_after_first = len(self.transport.move_calls)
        self.store.upload(self.local, run_id="run-001", shard_id="s1",
                          tool="mutmut", logical_path="p/b.json")
        self.assertEqual(len(self.transport.move_calls), move_calls_after_first,
                         "SSH mv must NOT be called again for duplicate blob")

    def test_two_uploads_produce_two_manifest_entries(self):
        self.store.upload(self.local, run_id="run-001", shard_id="s0",
                          tool="mutmut", logical_path="p/a.json")
        self.store.upload(self.local, run_id="run-001", shard_id="s1",
                          tool="mutmut", logical_path="p/b.json")
        self.assertEqual(len(self.transport.append_calls), 2,
                         "Two uploads of identical bytes must produce two manifest entries")

    def test_both_manifest_entries_reference_same_sha256(self):
        e1 = self.store.upload(self.local, run_id="run-001", shard_id="s0",
                               tool="mutmut", logical_path="p/a.json")
        e2 = self.store.upload(self.local, run_id="run-001", shard_id="s1",
                               tool="mutmut", logical_path="p/b.json")
        self.assertEqual(e1["sha256"], e2["sha256"])


# ---------------------------------------------------------------------------
# TestUploadFailure
# ---------------------------------------------------------------------------

class TestUploadFailure(TestCase):

    def setUp(self):
        if mbs is None:
            self.skipTest("mint_blob_store.py not yet written")
        self.local = _make_tmp_file(b"fail me")

    def tearDown(self):
        os.unlink(self.local)

    def test_scp_failure_raises(self):
        transport = _FakeTransport(fail_upload=True)
        store = mbs.MintBlobStore("mint", "user", transport=transport)
        with self.assertRaises(RuntimeError):
            store.upload(self.local, run_id="r1", shard_id="s0",
                         tool="test", logical_path="p.json")

    def test_mv_failure_raises(self):
        transport = _FakeTransport(fail_move=True)
        store = mbs.MintBlobStore("mint", "user", transport=transport)
        with self.assertRaises(RuntimeError):
            store.upload(self.local, run_id="r1", shard_id="s0",
                         tool="test", logical_path="p.json")


# ---------------------------------------------------------------------------
# TestCheckManifests (merge-shard-outputs logic)
# ---------------------------------------------------------------------------

class TestCheckManifests(TestCase):
    """Missing required blobs → non-empty error list."""

    def setUp(self):
        if mso is None:
            self.skipTest("merge_shard_outputs.py not yet written")

    def _entry(self, sha: str, required: bool = True) -> dict:
        return {
            "run_id": "run-001",
            "worker": "windows",
            "shard_id": "s0",
            "tool": "mutmut",
            "logical_path": "p/results.json",
            "sha256": sha,
            "size_bytes": 42,
            "media_type": "application/json",
            "created_at": "2026-05-27T12:00:00Z",
            "required_for_merge": required,
        }

    def test_no_errors_when_all_blobs_present(self):
        sha = _sha256(b"present")
        entries = [self._entry(sha)]
        errors = mso.check_manifests(entries, blob_exists=lambda s: s == sha)
        self.assertEqual(errors, [])

    def test_error_when_required_blob_missing(self):
        sha = _sha256(b"missing")
        entries = [self._entry(sha, required=True)]
        errors = mso.check_manifests(entries, blob_exists=lambda s: False)
        self.assertGreater(len(errors), 0)

    def test_no_error_when_optional_blob_missing(self):
        sha = _sha256(b"optional")
        entries = [self._entry(sha, required=False)]
        errors = mso.check_manifests(entries, blob_exists=lambda s: False)
        self.assertEqual(errors, [])

    def test_error_message_contains_sha256(self):
        sha = _sha256(b"gone")
        entries = [self._entry(sha, required=True)]
        errors = mso.check_manifests(entries, blob_exists=lambda s: False)
        self.assertTrue(any(sha in e for e in errors))


# ---------------------------------------------------------------------------
# TestCollectGarbage (mint_gc logic)
# ---------------------------------------------------------------------------

class TestCollectGarbage(TestCase):
    """Retained-manifest blobs must never be in the delete list."""

    def setUp(self):
        if mgc is None:
            self.skipTest("mint_gc.py not yet written")

    def test_referenced_blob_not_deleted(self):
        sha = _sha256(b"keep me")
        all_blobs = [f"/srv/xf/artifacts/blob-store/sha256/{sha[:2]}/{sha}"]
        retained = {sha}
        to_delete = mgc.collect_garbage(all_blobs, retained_sha256s=retained,
                                        grace_period_days=7)
        self.assertNotIn(all_blobs[0], to_delete,
                         "collect_garbage must not delete a referenced blob")

    def test_unreferenced_blob_is_deleted(self):
        sha = _sha256(b"gone")
        all_blobs = [f"/srv/xf/artifacts/blob-store/sha256/{sha[:2]}/{sha}"]
        retained: set[str] = set()
        to_delete = mgc.collect_garbage(all_blobs, retained_sha256s=retained,
                                        grace_period_days=0)
        self.assertIn(all_blobs[0], to_delete)

    def test_empty_blob_list_returns_empty(self):
        result = mgc.collect_garbage([], retained_sha256s=set(), grace_period_days=7)
        self.assertEqual(result, [])

    def test_all_referenced_returns_empty_delete_list(self):
        sha_a = _sha256(b"a")
        sha_b = _sha256(b"b")
        all_blobs = [
            f"/srv/xf/artifacts/blob-store/sha256/{sha_a[:2]}/{sha_a}",
            f"/srv/xf/artifacts/blob-store/sha256/{sha_b[:2]}/{sha_b}",
        ]
        retained = {sha_a, sha_b}
        to_delete = mgc.collect_garbage(all_blobs, retained_sha256s=retained,
                                        grace_period_days=0)
        self.assertEqual(to_delete, [],
                         "No blobs should be deleted when all are referenced")
