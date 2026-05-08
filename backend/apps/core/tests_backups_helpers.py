"""Focused tests for database backup helper functions."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core import backups


_DB_SETTINGS = {
    "HOST": "db",
    "PORT": "5433",
    "USER": "xf_user",
    "NAME": "xf_db",
    "PASSWORD": "secret",
}


class CheckDiskPressureTests(SimpleTestCase):
    def test_accepts_free_space_at_threshold(self) -> None:
        with patch("apps.core.backups.disk_free_bytes") as disk_free:
            disk_free.return_value = backups.MIN_FREE_BYTES_FOR_BACKUP

            self.assertTrue(backups._check_disk_pressure_or_skip(Path("backups")))

    def test_rejects_low_free_space(self) -> None:
        with patch("apps.core.backups.disk_free_bytes", return_value=1):
            with self.assertLogs("apps.core.backups", level="WARNING") as logs:
                result = backups._check_disk_pressure_or_skip(Path("backups"))

        self.assertFalse(result)
        self.assertIn("skipped", logs.output[0])

    def test_treats_unknown_free_space_as_low(self) -> None:
        with patch("apps.core.backups.disk_free_bytes", return_value=0):
            self.assertFalse(backups._check_disk_pressure_or_skip(Path("backups")))


class MakeSnapshotPathTests(SimpleTestCase):
    def test_uses_backup_dir_prefix_and_suffix(self) -> None:
        path = backups._make_snapshot_path(Path("backups"))

        self.assertEqual(path.parent, Path("backups"))
        self.assertTrue(path.name.startswith("snapshot-"))
        self.assertTrue(path.name.endswith(".dump"))

    def test_embeds_sortable_timestamp(self) -> None:
        path = backups._make_snapshot_path(Path("backups"))

        self.assertRegex(path.name, r"^snapshot-\d{8}-\d{6}\.dump$")


class BuildPgArgvBaseTests(SimpleTestCase):
    def test_builds_connection_arguments_in_order(self) -> None:
        argv, _env = backups._build_pg_argv_base(_DB_SETTINGS)

        self.assertEqual(
            argv,
            ["-h", "db", "-p", "5433", "-U", "xf_user", "-d", "xf_db"],
        )

    def test_keeps_password_out_of_arguments(self) -> None:
        argv, env = backups._build_pg_argv_base(_DB_SETTINGS)

        self.assertNotIn("secret", argv)
        self.assertEqual(env["PGPASSWORD"], "secret")

    def test_skips_empty_password_environment(self) -> None:
        db_settings = {**_DB_SETTINGS, "PASSWORD": ""}

        _argv, env = backups._build_pg_argv_base(db_settings)

        self.assertNotIn("PGPASSWORD", env)


class BuildPgDumpCommandTests(SimpleTestCase):
    def test_builds_pg_dump_custom_format_command(self) -> None:
        output_file = Path("backups/snapshot.dump")

        argv, _env = backups._build_pg_dump_command(
            db_settings=_DB_SETTINGS,
            output_file=output_file,
        )

        self.assertEqual(argv[0], "pg_dump")
        self.assertIn("-Fc", argv)
        self.assertIn("--no-owner", argv)
        self.assertEqual(argv[-2:], ["-f", str(output_file)])

    def test_returns_environment_from_base_builder(self) -> None:
        _argv, env = backups._build_pg_dump_command(
            db_settings=_DB_SETTINGS,
            output_file=Path("snapshot.dump"),
        )

        self.assertEqual(env["PGPASSWORD"], "secret")


class BuildPgRestoreCommandTests(SimpleTestCase):
    def test_builds_pg_restore_clean_command(self) -> None:
        snapshot_path = Path("backups/snapshot.dump")

        argv, _env = backups._build_pg_restore_command(
            db_settings=_DB_SETTINGS,
            snapshot_path=snapshot_path,
        )

        self.assertEqual(argv[0], "pg_restore")
        self.assertIn("--clean", argv)
        self.assertIn("--if-exists", argv)
        self.assertEqual(argv[-1], str(snapshot_path))

    def test_returns_environment_from_base_builder(self) -> None:
        _argv, env = backups._build_pg_restore_command(
            db_settings=_DB_SETTINGS,
            snapshot_path=Path("snapshot.dump"),
        )

        self.assertEqual(env["PGPASSWORD"], "secret")


class RunPgDumpTests(SimpleTestCase):
    def test_success_returns_true(self) -> None:
        completed = subprocess.CompletedProcess(["pg_dump"], 0, "", "")
        with patch("apps.core.backups.subprocess.run", return_value=completed):
            result = backups._run_pg_dump(
                argv=["pg_dump"],
                env={},
                output_file=Path("snapshot.dump"),
                timeout_seconds=3,
            )

        self.assertTrue(result)

    def test_missing_binary_returns_false(self) -> None:
        with patch("apps.core.backups.subprocess.run", side_effect=FileNotFoundError):
            with self.assertLogs("apps.core.backups", level="ERROR") as logs:
                result = backups._run_pg_dump(
                    argv=["pg_dump"],
                    env={},
                    output_file=Path("snapshot.dump"),
                    timeout_seconds=3,
                )

        self.assertFalse(result)
        self.assertIn("pg_dump binary not found", logs.output[0])

    def test_timeout_cleans_partial_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "snapshot.dump"
            output_file.write_text("partial", encoding="utf-8")

            with patch(
                "apps.core.backups.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["pg_dump"], 3),
            ):
                result = backups._run_pg_dump(
                    argv=["pg_dump"],
                    env={},
                    output_file=output_file,
                    timeout_seconds=3,
                )

            self.assertFalse(result)
            self.assertFalse(output_file.exists())

    def test_non_zero_exit_cleans_partial_file_and_truncates_stderr(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "snapshot.dump"
            output_file.write_text("partial", encoding="utf-8")
            stderr = "x" * (backups._STDERR_LOG_TRUNCATE + 10)
            completed = subprocess.CompletedProcess(["pg_dump"], 2, "", stderr)

            with patch("apps.core.backups.subprocess.run", return_value=completed):
                with self.assertLogs("apps.core.backups", level="ERROR") as logs:
                    result = backups._run_pg_dump(
                        argv=["pg_dump"],
                        env={},
                        output_file=output_file,
                        timeout_seconds=3,
                    )

            self.assertFalse(result)
            self.assertFalse(output_file.exists())
            self.assertLessEqual(
                len(logs.records[0].args[1]),
                backups._STDERR_LOG_TRUNCATE,
            )


class VerifyDumpOutputTests(SimpleTestCase):
    def test_accepts_existing_non_empty_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "snapshot.dump"
            output_file.write_text("ok", encoding="utf-8")

            self.assertTrue(backups._verify_dump_output(output_file))

    def test_rejects_missing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "missing.dump"

            self.assertFalse(backups._verify_dump_output(output_file))

    def test_rejects_empty_file(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "snapshot.dump"
            output_file.touch()

            self.assertFalse(backups._verify_dump_output(output_file))


class ValidateRestorePathTests(SimpleTestCase):
    def test_existing_path_resolves_absolute(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "snapshot.dump"
            snapshot_path.write_text("ok", encoding="utf-8")

            result = backups._validate_restore_path(snapshot_path)

        self.assertEqual(result, snapshot_path.resolve())

    def test_missing_path_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.dump"

            self.assertIsNone(backups._validate_restore_path(missing))

    def test_relative_path_resolves(self) -> None:
        with TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            snapshot_path = Path(tmp) / "snapshot.dump"
            snapshot_path.write_text("ok", encoding="utf-8")
            os.chdir(tmp)
            try:
                result = backups._validate_restore_path(Path("snapshot.dump"))
            finally:
                os.chdir(cwd)

        self.assertEqual(result, snapshot_path.resolve())


class RunPgRestoreTests(SimpleTestCase):
    def test_success_returns_completed_process(self) -> None:
        completed = subprocess.CompletedProcess(["pg_restore"], 0, "", "")
        with patch("apps.core.backups.subprocess.run", return_value=completed):
            result = backups._run_pg_restore(
                argv=["pg_restore"],
                env={},
                timeout_seconds=3,
            )

        self.assertIs(result, completed)

    def test_missing_binary_returns_none(self) -> None:
        with patch("apps.core.backups.subprocess.run", side_effect=FileNotFoundError):
            result = backups._run_pg_restore(
                argv=["pg_restore"],
                env={},
                timeout_seconds=3,
            )

        self.assertIsNone(result)

    def test_timeout_returns_none(self) -> None:
        with patch(
            "apps.core.backups.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["pg_restore"], 3),
        ):
            result = backups._run_pg_restore(
                argv=["pg_restore"],
                env={},
                timeout_seconds=3,
            )

        self.assertIsNone(result)


class CheckRestoreResultTests(SimpleTestCase):
    def test_return_code_zero_is_success(self) -> None:
        result = subprocess.CompletedProcess(["pg_restore"], 0, "", "")

        self.assertTrue(backups._check_restore_result(result, "snapshot.dump"))

    def test_return_code_one_is_accepted_warning(self) -> None:
        result = subprocess.CompletedProcess(["pg_restore"], 1, "", "warning")

        self.assertTrue(backups._check_restore_result(result, "snapshot.dump"))

    def test_return_code_two_is_failure(self) -> None:
        result = subprocess.CompletedProcess(["pg_restore"], 2, "", "fatal")

        self.assertFalse(backups._check_restore_result(result, "snapshot.dump"))


class RestoreFromSnapshotTopLevelTests(SimpleTestCase):
    def test_requires_destructive_confirmation(self) -> None:
        with self.assertRaises(ValueError):
            backups.restore_from_snapshot(snapshot_path=Path("snapshot.dump"))

    def test_returns_false_when_path_invalid(self) -> None:
        with patch("apps.core.backups._validate_restore_path", return_value=None):
            result = backups.restore_from_snapshot(
                snapshot_path=Path("missing.dump"),
                confirm_destructive=True,
            )

        self.assertFalse(result)


class CreateSnapshotTopLevelTests(SimpleTestCase):
    def test_returns_none_when_disk_check_fails(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch(
                "apps.core.backups._check_disk_pressure_or_skip", return_value=False
            ):
                result = backups.create_snapshot(backup_dir=Path(tmp))

        self.assertIsNone(result)

    def test_returns_path_when_all_steps_succeed(self) -> None:
        with TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "snapshot-20260507-120000.dump"
            output_file.write_text("ok", encoding="utf-8")
            patches = (
                patch(
                    "apps.core.backups._check_disk_pressure_or_skip", return_value=True
                ),
                patch(
                    "apps.core.backups._make_snapshot_path", return_value=output_file
                ),
                patch("apps.core.backups._run_pg_dump", return_value=True),
                patch("apps.core.backups._verify_dump_output", return_value=True),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                result = backups.create_snapshot(backup_dir=Path(tmp))

        self.assertEqual(result, output_file)


class SnapshotNamePatternTests(SimpleTestCase):
    def test_pattern_is_strict_enough_for_lexicographic_sort(self) -> None:
        pattern = re.compile(r"^snapshot-\d{8}-\d{6}\.dump$")

        self.assertIsNotNone(pattern.match(backups._make_snapshot_path(Path(".")).name))
