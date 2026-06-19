#!/usr/bin/env python3
"""Tests for the content-hash quality cache (skip unchanged files)."""

from __future__ import annotations

import json
import os
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import quality_cache
from scripts.quality_cache import QualityCache

_DAY = 24 * 3600


class _TempRepo:
    """Tiny disposable repo root with an audit/ dir and one source file."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "audit").mkdir()
        self.source = self.root / "backend" / "apps" / "demo" / "thing.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("VALUE = 1\n", encoding="utf-8")

    def cleanup(self) -> None:
        self._tmp.cleanup()


class QualityCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _TempRepo()
        self.addCleanup(self.repo.cleanup)
        os.environ.pop("XF_QUALITY_CACHE", None)

    def _subjects(self, cache: QualityCache) -> dict[str, str]:
        name = self.repo.source.as_posix()
        return {name: cache.subject_hash_for_files([self.repo.source])}

    def _run_cli(self, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["quality_cache.py", *args]
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = quality_cache.main()
        except SystemExit as exc:
            code = int(exc.code or 0)
        finally:
            sys.argv = old_argv
        return code, stdout.getvalue(), stderr.getvalue()

    def test_recorded_pass_is_skipped_on_next_run(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        to_run, skipped = cache.filter("ruff", self._subjects(cache))
        self.assertEqual(skipped, [])
        cache.record("ruff", list(self._subjects(cache).values()))

        fresh = QualityCache(self.repo.root, now=2000.0)
        to_run, skipped = fresh.filter("ruff", self._subjects(fresh))
        self.assertEqual(to_run, [])
        self.assertEqual(len(skipped), 1)

    def test_changed_content_misses_the_cache(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))
        self.repo.source.write_text("VALUE = 2\n", encoding="utf-8")

        fresh = QualityCache(self.repo.root, now=2000.0)
        to_run, skipped = fresh.filter("ruff", self._subjects(fresh))
        self.assertEqual(skipped, [])
        self.assertEqual(len(to_run), 1)

    def test_different_tool_misses_the_cache(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))

        fresh = QualityCache(self.repo.root, now=2000.0)
        to_run, _skipped = fresh.filter("mypy", self._subjects(fresh))
        self.assertEqual(len(to_run), 1)

    def test_unrecorded_subjects_always_run(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        to_run, skipped = cache.filter("ruff", self._subjects(cache))
        self.assertEqual(len(to_run), 1)
        self.assertEqual(skipped, [])

    def test_expired_rows_are_dropped(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))

        later = QualityCache(self.repo.root, now=1000.0 + 15 * _DAY)
        to_run, skipped = later.filter("ruff", self._subjects(later))
        self.assertEqual(skipped, [])
        self.assertEqual(len(to_run), 1)

    def test_config_change_invalidates_everything(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))
        config = self.repo.root / "backend" / "pytest.ini"
        config.write_text("[pytest]\naddopts = -q\n", encoding="utf-8")

        fresh = QualityCache(self.repo.root, now=2000.0)
        to_run, skipped = fresh.filter("ruff", self._subjects(fresh))
        self.assertEqual(skipped, [])
        self.assertEqual(len(to_run), 1)

    def test_env_var_zero_disables_lookup_and_record(self) -> None:
        os.environ["XF_QUALITY_CACHE"] = "0"
        self.addCleanup(os.environ.pop, "XF_QUALITY_CACHE", None)
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))
        self.assertFalse(cache.path.exists())

        to_run, skipped = cache.filter("ruff", self._subjects(cache))
        self.assertEqual(skipped, [])
        self.assertEqual(len(to_run), 1)

    def test_corrupt_lines_are_ignored(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("ruff", list(self._subjects(cache).values()))
        with cache.path.open("a", encoding="utf-8") as handle:
            handle.write("this is not json\n{\"key\": 1}\n")

        fresh = QualityCache(self.repo.root, now=2000.0)
        _to_run, skipped = fresh.filter("ruff", self._subjects(fresh))
        self.assertEqual(len(skipped), 1)

    def test_compaction_keeps_the_file_bounded(self) -> None:
        original = quality_cache._MAX_ROWS
        quality_cache._MAX_ROWS = 3
        self.addCleanup(setattr, quality_cache, "_MAX_ROWS", original)
        cache = QualityCache(self.repo.root, now=1000.0)
        hashes = [f"subject-{n}" for n in range(8)]
        for subject in hashes:
            cache.record("ruff", [subject])

        line_count = len(cache.path.read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(line_count, 8)
        fresh = QualityCache(self.repo.root, now=1500.0)
        self.assertTrue(all(fresh.has_pass("ruff", s) for s in hashes))

    def test_cli_filter_and_record_pairs_roundtrip(self) -> None:
        pair_file = self.repo.root / "pairs.txt"
        test_file = self.repo.root / "backend" / "apps" / "demo" / "test_thing.py"
        test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        pair_line = f"{self.repo.source.as_posix()}\t{test_file.as_posix()}\n"
        pair_file.write_text(pair_line, encoding="utf-8")
        base: list[str] = []

        first_code, first_stdout, first_stderr = self._run_cli(
            base + [
                "filter-pairs",
                "--root",
                str(self.repo.root),
                "--tool",
                "mutmut",
                "--pairs-file",
                str(pair_file),
            ]
        )
        self.assertEqual(first_code, 0, first_stderr)
        self.assertIn(self.repo.source.as_posix(), first_stdout)

        record_code, _record_stdout, record_stderr = self._run_cli(
            base + [
                "record-pairs",
                "--root",
                str(self.repo.root),
                "--tool",
                "mutmut",
                "--pairs-file",
                str(pair_file),
            ]
        )
        self.assertEqual(record_code, 0, record_stderr)
        second_code, second_stdout, second_stderr = self._run_cli(
            base + [
                "filter-pairs",
                "--root",
                str(self.repo.root),
                "--tool",
                "mutmut",
                "--pairs-file",
                str(pair_file),
            ]
        )
        self.assertEqual(second_code, 0, second_stderr)
        self.assertEqual(second_stdout.strip(), "")

    def test_missing_files_hash_as_empty_not_crash(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        ghost = self.repo.root / "backend" / "apps" / "demo" / "ghost.py"
        subject = cache.subject_hash_for_files([ghost])
        self.assertTrue(subject)

    def test_rows_record_the_tool_name_for_debugging(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        cache.record("pytest", ["subject-a"])
        row = json.loads(cache.path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["tool"], "pytest")

    def test_gate_subject_changes_when_scoped_file_changes(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        first = cache.subject_hash_for_gate([self.repo.source], "python scripts/example.py")
        self.repo.source.write_text("VALUE = 3\n", encoding="utf-8")
        second = cache.subject_hash_for_gate([self.repo.source], "python scripts/example.py")

        self.assertNotEqual(first, second)

    def test_cli_gate_check_records_pass_and_skips_same_scope(self) -> None:
        env = os.environ.copy()
        env["COMMIT_SCOPE_PATHS"] = self.repo.source.relative_to(self.repo.root).as_posix()
        old_scope = os.environ.get("COMMIT_SCOPE_PATHS")
        os.environ["COMMIT_SCOPE_PATHS"] = env["COMMIT_SCOPE_PATHS"]
        self.addCleanup(
            lambda: os.environ.pop("COMMIT_SCOPE_PATHS", None)
            if old_scope is None
            else os.environ.__setitem__("COMMIT_SCOPE_PATHS", old_scope)
        )
        base: list[str] = []
        opts = [
            "--root",
            str(self.repo.root),
            "--tool",
            "gate:demo",
            "--paths-env",
            "COMMIT_SCOPE_PATHS",
            "--command-text",
            "python scripts/example.py",
        ]

        miss_code, _miss_stdout, _miss_stderr = self._run_cli(base + ["check-gate", *opts])
        self.assertEqual(miss_code, 1)

        record_code, _record_stdout, record_stderr = self._run_cli(
            base + ["record-gate", *opts]
        )
        self.assertEqual(record_code, 0, record_stderr)
        hit_code, hit_stdout, _hit_stderr = self._run_cli(base + ["check-gate", *opts])

        self.assertEqual(hit_code, 0)
        self.assertIn("quality-cache:gate-pass-cached gate:demo", hit_stdout)

    def test_gate_ttl_forces_stale_health_checks_to_rerun(self) -> None:
        cache = QualityCache(self.repo.root, now=1000.0)
        subject = cache.subject_hash_for_gate([self.repo.source], "python health.py")
        cache.record("gate:health", [subject])

        fresh = QualityCache(self.repo.root, now=5000.0)

        self.assertFalse(fresh.has_pass("gate:health", subject, max_age_seconds=3600))
        self.assertTrue(fresh.has_pass("gate:health", subject, max_age_seconds=5000))

    def test_gate_subject_includes_existing_command_file(self) -> None:
        helper = self.repo.root / "scripts" / "example.py"
        helper.parent.mkdir()
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        cache = QualityCache(self.repo.root, now=1000.0)
        first = cache.subject_hash_for_gate([], "python scripts/example.py")
        helper.write_text("VALUE = 2\n", encoding="utf-8")

        self.assertNotEqual(first, cache.subject_hash_for_gate([], "python scripts/example.py"))


if __name__ == "__main__":
    unittest.main()
