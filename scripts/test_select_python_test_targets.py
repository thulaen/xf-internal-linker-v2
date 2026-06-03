#!/usr/bin/env python3
"""Tests for selecting focused backend pytest targets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from select_python_test_targets import select_targets


class SelectPythonTestTargetsTests(unittest.TestCase):
    def test_prefers_command_specific_test_over_whole_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = (
                root
                / "backend/apps/auto_issues/management/commands/preflight_tdd.py"
            )
            focused_test = root / "backend/apps/auto_issues/tests/test_preflight_tdd.py"
            broad_test = root / "backend/apps/auto_issues/tests/test_session_close.py"
            app_root_test = root / "backend/apps/auto_issues/tests_loki_picker.py"
            for path in (command, focused_test, broad_test, app_root_test):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# test fixture\n", encoding="utf-8")

            targets, missing = select_targets(
                root,
                [
                    "backend/apps/auto_issues/management/commands/preflight_tdd.py",
                ],
            )

        self.assertEqual(missing, [])
        self.assertEqual(targets, ["apps/auto_issues/tests/test_preflight_tdd.py"])

    def test_reports_each_file_without_a_focused_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = (
                root
                / "backend/apps/auto_issues/management/commands/preflight_tdd.py"
            )
            helper = root / "backend/apps/auto_issues/services/resolved_issue_index.py"
            focused_test = root / "backend/apps/auto_issues/tests/test_preflight_tdd.py"
            broad_test = root / "backend/apps/auto_issues/tests/test_session_close.py"
            for path in (command, helper, focused_test, broad_test):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# test fixture\n", encoding="utf-8")

            targets, missing = select_targets(
                root,
                [
                    "backend/apps/auto_issues/management/commands/preflight_tdd.py",
                    "backend/apps/auto_issues/services/resolved_issue_index.py",
                ],
            )

        self.assertEqual(
            missing,
            ["apps/auto_issues/services/resolved_issue_index.py"],
        )
        self.assertEqual(targets, ["apps/auto_issues/tests/test_preflight_tdd.py"])

    def test_missing_focused_target_does_not_select_whole_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = root / "backend/apps/auto_issues/services/resolved_issue_index.py"
            broad_test = root / "backend/apps/auto_issues/tests/test_session_close.py"
            for path in (helper, broad_test):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# test fixture\n", encoding="utf-8")

            targets, missing = select_targets(
                root,
                ["backend/apps/auto_issues/services/resolved_issue_index.py"],
            )

        self.assertEqual(targets, [])
        self.assertEqual(missing, ["apps/auto_issues/services/resolved_issue_index.py"])

    def test_finds_tests_that_import_changed_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "backend/apps/auto_issues/services/fingerprinting.py"
            focused_test = (
                root
                / "backend/apps/auto_issues/tests/test_canonical_fingerprint_path_distinct.py"
            )
            source.parent.mkdir(parents=True, exist_ok=True)
            focused_test.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("def canonical_fingerprint():\n    return 'x'\n", encoding="utf-8")
            focused_test.write_text(
                "from apps.auto_issues.services.fingerprinting import "
                "canonical_fingerprint\n",
                encoding="utf-8",
            )

            targets, missing = select_targets(
                root,
                ["backend/apps/auto_issues/services/fingerprinting.py"],
            )

        self.assertEqual(missing, [])
        self.assertEqual(
            targets,
            ["apps/auto_issues/tests/test_canonical_fingerprint_path_distinct.py"],
        )

    def test_finds_app_level_command_tests_by_call_command_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = root / "backend/apps/paper_trail/management/commands/defer_work.py"
            focused_test = root / "backend/apps/paper_trail/tests_defer_work_command.py"
            for path in (command, focused_test):
                path.parent.mkdir(parents=True, exist_ok=True)
            command.write_text("# command fixture\n", encoding="utf-8")
            focused_test.write_text(
                "from django.core.management import call_command\n"
                "call_command('defer_work')\n",
                encoding="utf-8",
            )

            targets, missing = select_targets(
                root,
                ["backend/apps/paper_trail/management/commands/defer_work.py"],
            )

        self.assertEqual(missing, [])
        self.assertEqual(targets, ["apps/paper_trail/tests_defer_work_command.py"])

    def test_finds_multiline_call_command_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = root / "backend/apps/audit/management/commands/migrate_audit_to_sqlite.py"
            focused_test = root / "backend/apps/audit/tests_audit_sqlite_lookup.py"
            for path in (command, focused_test):
                path.parent.mkdir(parents=True, exist_ok=True)
            command.write_text("# command fixture\n", encoding="utf-8")
            focused_test.write_text(
                "from django.core.management import call_command\n"
                "call_command(\n"
                "    \"migrate_audit_to_sqlite\",\n"
                ")\n",
                encoding="utf-8",
            )

            targets, missing = select_targets(
                root,
                ["backend/apps/audit/management/commands/migrate_audit_to_sqlite.py"],
            )

        self.assertEqual(missing, [])
        self.assertEqual(targets, ["apps/audit/tests_audit_sqlite_lookup.py"])

    def test_package_markers_do_not_require_pytest_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "backend/apps/audit/management/__init__.py"
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_text("", encoding="utf-8")

            targets, missing = select_targets(
                root,
                ["backend/apps/audit/management/__init__.py"],
            )

        self.assertEqual(targets, [])
        self.assertEqual(missing, [])

    def test_generated_sidecar_stubs_use_shared_contract_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / "backend/apps/_sidecars_pb/attrouted/attrouted_pb2.py"
            contract_test = (
                root / "backend/apps/_sidecars_shared/tests_sidecar_contract.py"
            )
            for path in (stub, contract_test):
                path.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text("# Generated by protoc\n", encoding="utf-8")
            contract_test.write_text("# focused sidecar contract test\n", encoding="utf-8")

            targets, missing = select_targets(
                root,
                ["backend/apps/_sidecars_pb/attrouted/attrouted_pb2.py"],
            )

        self.assertEqual(missing, [])
        self.assertEqual(targets, ["apps/_sidecars_shared/tests_sidecar_contract.py"])

    def test_dirty_turbo_python_paths_have_focused_targets(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        paths = [
            "backend/apps/auto_issues/_sidecars/schemard_client.py",
            "backend/apps/auto_issues/_sidecars/snapshotd_client.py",
            "backend/apps/auto_issues/management/commands/refresh_session_start_payload.py",
            "backend/apps/auto_issues/management/commands/rotate_scope_log.py",
            "backend/apps/work_queue/services/correlation.py",
            "backend/apps/work_queue/services/gui_projection.py",
            "backend/apps/work_queue/services/items.py",
            "backend/apps/work_queue/services/remediation.py",
        ]

        targets, missing = select_targets(repo_root, paths)

        self.assertEqual(missing, [])
        self.assertIn("apps/auto_issues/tests/test_sidecar_clients.py", targets)
        self.assertIn("apps/auto_issues/tests_session_start_payload.py", targets)
        self.assertIn("apps/auto_issues/tests_rotate_scope_log.py", targets)
        self.assertIn("apps/work_queue/tests_services.py", targets)


if __name__ == "__main__":
    unittest.main()
