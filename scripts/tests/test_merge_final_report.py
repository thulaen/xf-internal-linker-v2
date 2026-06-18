"""Tests for merge_shard_outputs.py — final merge validation.

BDD:
  Given a set of shard manifest entries including some failed shards
  When check_manifests() and check_failed_shards() are called
  Then missing required blobs produce errors
  And failed required shards without an autoissue_id produce errors
  And the merge command exits non-zero when any error exists
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase


_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = _SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


try:
    mso = _load("merge_shard_outputs")
except FileNotFoundError:
    mso = None


_GOOD_ENTRY = {
    "run_id": "run-001",
    "worker": "windows",
    "shard_id": "shard-0",
    "tool": "mutmut",
    "logical_path": "mutation/results.json",
    "sha256": "a" * 64,
    "size_bytes": 1234,
    "media_type": "application/json",
    "required_for_merge": True,
}

_FAILED_WITH_ISSUE = {
    **_GOOD_ENTRY,
    "sha256": "b" * 64,
    "logical_path": "mutation/failed.json",
    "shard_id": "shard-1",
    "failed": True,
    "autoissue_id": 42,
}

_FAILED_NO_ISSUE = {
    **_GOOD_ENTRY,
    "sha256": "c" * 64,
    "logical_path": "mutation/failed2.json",
    "shard_id": "shard-2",
    "failed": True,
}


class TestModuleExists(TestCase):
    def test_module_importable(self) -> None:
        self.assertIsNotNone(mso, "merge_shard_outputs.py must exist under scripts/")

    def test_check_manifests_exists(self) -> None:
        self.assertTrue(callable(mso.check_manifests))

    def test_check_failed_shards_exists(self) -> None:
        self.assertTrue(
            callable(getattr(mso, "check_failed_shards", None)),
            "check_failed_shards() must exist in merge_shard_outputs.py",
        )


class TestCheckManifests(TestCase):
    def _blob_all_present(self, sha256: str) -> bool:
        return True

    def _blob_none_present(self, sha256: str) -> bool:
        return False

    def test_all_blobs_present_returns_empty(self) -> None:
        errors = mso.check_manifests([_GOOD_ENTRY], self._blob_all_present)
        self.assertEqual(errors, [])

    def test_missing_required_blob_returns_error(self) -> None:
        errors = mso.check_manifests([_GOOD_ENTRY], self._blob_none_present)
        self.assertEqual(len(errors), 1)
        self.assertIn(_GOOD_ENTRY["sha256"], errors[0])

    def test_optional_entries_not_checked(self) -> None:
        optional = {**_GOOD_ENTRY, "required_for_merge": False}
        errors = mso.check_manifests([optional], self._blob_none_present)
        self.assertEqual(errors, [])


class TestCheckFailedShards(TestCase):
    def test_no_failures_returns_empty(self) -> None:
        errors = mso.check_failed_shards([_GOOD_ENTRY])
        self.assertEqual(errors, [])

    def test_failed_shard_with_autoissue_id_returns_empty(self) -> None:
        errors = mso.check_failed_shards([_FAILED_WITH_ISSUE])
        self.assertEqual(errors, [])

    def test_failed_required_shard_without_autoissue_raises_error(self) -> None:
        errors = mso.check_failed_shards([_FAILED_NO_ISSUE])
        self.assertEqual(len(errors), 1)
        self.assertIn("shard-2", errors[0])
        self.assertIn("autoissue_id", errors[0])

    def test_optional_failed_shard_without_autoissue_returns_empty(self) -> None:
        optional_failed = {**_FAILED_NO_ISSUE, "required_for_merge": False}
        errors = mso.check_failed_shards([optional_failed])
        self.assertEqual(errors, [])

    def test_multiple_entries_only_flags_failed_required(self) -> None:
        entries = [_GOOD_ENTRY, _FAILED_WITH_ISSUE, _FAILED_NO_ISSUE]
        errors = mso.check_failed_shards(entries)
        self.assertEqual(len(errors), 1)
        self.assertIn("shard-2", errors[0])


class TestFinalReport(TestCase):
    def test_render_final_report_counts_errors(self) -> None:
        entries = [_GOOD_ENTRY, _FAILED_NO_ISSUE]
        errors = mso.check_failed_shards(entries)
        report = mso.render_final_report("run-001", entries, errors)
        self.assertIn("Status: failed", report)
        self.assertIn("Manifest entries checked: 2", report)
        self.assertIn("Merge errors: 1", report)

    def test_summarize_entries_passed_when_no_errors(self) -> None:
        summary = mso.summarize_entries([_GOOD_ENTRY], [])
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["required_entries"], 1)
