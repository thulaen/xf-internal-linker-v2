"""Tests for the fast disk-backed resolved-issue lookup helper."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parent / "lookup_disk_index.py"
_SPEC = importlib.util.spec_from_file_location("lookup_disk_index", SCRIPT_PATH)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)


class PathNormalisationTests(unittest.TestCase):
    def test_backslashes_and_edges_are_normalised(self) -> None:
        self.assertEqual(
            _MOD.normalise_path("  /backend\\apps\\x.py/ "),
            "backend/apps/x.py",
        )


class IndexLoadTests(unittest.TestCase):
    def test_missing_index_returns_empty_map(self) -> None:
        missing = Path(tempfile.gettempdir()) / "missing-resolved-index.jsonl"
        missing.unlink(missing_ok=True)

        self.assertEqual(_MOD.load_index(missing), {})

    def test_malformed_rows_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            index_path = Path(raw_dir) / "index.jsonl"
            _write_jsonl(index_path, ["not-json", {"file_path": "a.py", "autoissue_id": 7}])

            index = _MOD.load_index(index_path)

        self.assertEqual(index["a.py"][0]["autoissue_id"], 7)

    def test_paths_are_keyed_after_normalisation(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            index_path = Path(raw_dir) / "index.jsonl"
            _write_jsonl(
                index_path,
                [{"file_path": "backend\\apps\\x.py", "autoissue_id": 3}],
            )

            index = _MOD.load_index(index_path)

        self.assertIn("backend/apps/x.py", index)


class LookupTests(unittest.TestCase):
    def test_lookup_returns_exact_path_matches(self) -> None:
        index = {
            "a.py": [{"autoissue_id": 1}],
            "a.py/child.py": [{"autoissue_id": 2}],
        }

        self.assertEqual(_MOD.lookup_area(index, "a.py"), [{"autoissue_id": 1}])

    def test_result_ids_ignore_missing_ids(self) -> None:
        rows = [{"autoissue_id": 2}, {"issue_title": "no id"}]

        self.assertEqual(_MOD.result_ids(rows), [2])


class AuditLogTests(unittest.TestCase):
    def test_append_audit_entry_writes_expected_schema(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            audit_path = Path(raw_dir) / "lookup.jsonl"
            row = _MOD.append_audit_entry(
                audit_path=audit_path,
                file_path="a.py",
                task_id="T1",
                agent="codex",
                rows=[{"autoissue_id": 9}],
            )
            saved = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(row["result_count"], 1)
        self.assertEqual(saved["result_ids"], [9])
        self.assertEqual(saved["task_id"], "T1")

    def test_task_id_uses_latest_preflight_marker(self) -> None:
        text = (
            "[TDD PREFLIGHT: session_id=11111111-1111-1111-1111-111111111111]\n"
            "[TDD PREFLIGHT: session_id=22222222-2222-2222-2222-222222222222]\n"
        )
        with tempfile.TemporaryDirectory() as raw_dir:
            handoff = Path(raw_dir) / "AGENT-HANDOFF.md"
            handoff.write_text(text, encoding="utf-8")

            self.assertEqual(
                _MOD.current_task_id(handoff),
                "22222222-2222-2222-2222-222222222222",
            )

    def test_task_id_falls_back_when_marker_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            handoff = Path(raw_dir) / "AGENT-HANDOFF.md"
            handoff.write_text("none", encoding="utf-8")

            self.assertTrue(_MOD.current_task_id(handoff).startswith("fallback-"))


class CliTests(unittest.TestCase):
    def test_cli_writes_one_audit_row_per_area(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            index_path = root / "index.jsonl"
            audit_path = root / "audit.jsonl"
            handoff_path = root / "AGENT-HANDOFF.md"
            handoff_path.write_text(
                "[TDD PREFLIGHT: session_id=33333333-3333-3333-3333-333333333333]\n",
                encoding="utf-8",
            )
            _write_jsonl(index_path, [{"file_path": "a.py", "autoissue_id": 4}])

            code = _MOD.main([
                "--index",
                str(index_path),
                "--audit-log",
                str(audit_path),
                "--handoff",
                str(handoff_path),
                "--area",
                "a.py",
                "--area",
                "missing.py",
                "--agent",
                "codex",
            ])

            lines = audit_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)

    def test_cli_requires_at_least_one_area(self) -> None:
        code = _MOD.main([])

        self.assertEqual(code, 2)

    def test_current_index_lookup_stays_under_budget(self) -> None:
        index_path = Path("audit/resolved_issues_index.jsonl")
        if not index_path.exists():
            self.skipTest("repository index not present")

        start = time.perf_counter()
        _MOD.load_index(index_path)
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertLess(elapsed_ms, 200)


def _write_jsonl(path: Path, rows: list[object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if isinstance(row, str):
                fh.write(row + "\n")
            else:
                fh.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    unittest.main()
