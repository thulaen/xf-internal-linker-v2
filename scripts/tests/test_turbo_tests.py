"""Tests for scripts/turbo_tests.py pure helpers.

BDD:
  Given a machine with an unknown transport
  When _run_shard_on_machine() runs
  Then it returns rc=1 and a "shard skipped" message (never silently passes)

  Given a shard result whose rc is None (thread crashed)
  When _merge_shard_results() runs on MSI
  Then it fails closed instead of rerunning locally
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "turbo_tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("turbo_tests", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["turbo_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


tt = _load()


class TestRunShardOnMachine(TestCase):
    def test_docker_local_refuses_msi_without_diagnostic(self) -> None:
        with mock.patch.object(tt.sys, "platform", "win32"), mock.patch.dict(
            tt.os.environ,
            {"XF_ALLOW_MSI_LOCAL_QUALITY": ""},
            clear=False,
        ):
            tt.os.environ.pop("XF_ALLOW_MSI_LOCAL_QUALITY", None)
            rc, out = tt._run_shard_on_machine(
                {"transport": "docker_local", "name": "windows"}, ["a.py"]
            )
        self.assertEqual(rc, 1)
        self.assertIn("MSI is dev-only", out)

    def test_docker_local_dispatches_local_for_diagnostic(self) -> None:
        with mock.patch.object(
            tt, "_run_shard_local", return_value=(0, "ok")
        ) as local, mock.patch.object(tt.sys, "platform", "win32"), mock.patch.dict(
            tt.os.environ,
            {"XF_ALLOW_MSI_LOCAL_QUALITY": "1"},
            clear=False,
        ):
            rc, out = tt._run_shard_on_machine(
                {"transport": "docker_local", "name": "windows"}, ["a.py"]
            )
        local.assert_called_once()
        self.assertEqual(rc, 0)

    def test_docker_context_dispatches_context(self) -> None:
        with mock.patch.object(
            tt, "_run_shard_context", return_value=(0, "ok")
        ) as ctx:
            tt._run_shard_on_machine(
                {"transport": "docker_context", "name": "mint", "context": "mint"},
                ["a.py"],
            )
        ctx.assert_called_once()

    def test_unknown_transport_returns_skip(self) -> None:
        rc, out = tt._run_shard_on_machine(
            {"transport": "carrier-pigeon", "name": "weird"}, ["a.py"]
        )
        self.assertEqual(rc, 1)
        self.assertIn("Unknown transport", out)


class TestMergeShardResults(TestCase):
    def test_all_pass_returns_zero(self) -> None:
        results = [
            {"machine": {"name": "w"}, "rc": 0},
            {"machine": {"name": "m"}, "rc": 0},
        ]
        self.assertEqual(tt._merge_shard_results(results), 0)

    def test_any_failure_returns_one(self) -> None:
        results = [
            {"machine": {"name": "w"}, "rc": 0},
            {"machine": {"name": "m"}, "rc": 2},
        ]
        self.assertEqual(tt._merge_shard_results(results), 1)

    def test_none_rc_fails_closed_on_msi(self) -> None:
        results = [{"machine": {"name": "w"}, "rc": None, "files": ["a.py"], "cmd": ""}]
        with mock.patch.object(tt.sys, "platform", "win32"), mock.patch.dict(
            tt.os.environ,
            {"XF_ALLOW_MSI_LOCAL_QUALITY": ""},
            clear=False,
        ):
            tt.os.environ.pop("XF_ALLOW_MSI_LOCAL_QUALITY", None)
            final = tt._merge_shard_results(results)
        self.assertEqual(final, 1)

    def test_none_rc_diagnostic_rerun_failure_returns_one(self) -> None:
        results = [{"machine": {"name": "w"}, "rc": None, "files": ["a.py"], "cmd": ""}]
        with mock.patch.object(tt, "_run_shard_local", return_value=(1, "rerun bad")), (
            mock.patch.object(tt.sys, "platform", "win32")
        ), mock.patch.dict(
            tt.os.environ,
            {"XF_ALLOW_MSI_LOCAL_QUALITY": "1"},
            clear=False,
        ):
            self.assertEqual(tt._merge_shard_results(results), 1)


class TestDryRunDiscovery(TestCase):
    def test_fast_discovery_reads_files_without_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            repo_root = Path(raw_root)
            test_dir = repo_root / "backend" / "apps" / "example"
            test_dir.mkdir(parents=True)
            (test_dir / "tests_fast.py").write_text(
                "from django.test import SimpleTestCase\n\n"
                "class ExampleTests(SimpleTestCase):\n"
                "    pass\n",
                encoding="utf-8",
            )
            (test_dir / "test_db.py").write_text(
                "from django.test import TestCase\n\n"
                "class DbTests(TestCase):\n"
                "    pass\n",
                encoding="utf-8",
            )
            (test_dir / "helper.py").write_text("SimpleTestCase\n", encoding="utf-8")

            with mock.patch.object(tt, "REPO_ROOT", repo_root), mock.patch.object(
                tt.subprocess,
                "run",
                side_effect=AssertionError("fast discovery must not call subprocess"),
            ):
                files = tt._discover_simpletest_files_fast()

        self.assertEqual(files, ["apps/example/tests_fast.py"])

    def test_dry_run_uses_fast_discovery(self) -> None:
        class FakeRouting:
            class RemoteUnavailableError(RuntimeError):
                pass

            def _select_machines(self, cfg: dict[str, object]) -> list[dict[str, object]]:
                return [{"name": "dell"}, {"name": "windows"}]

            def _partition_weighted(
                self,
                files: list[str],
                machines: list[dict[str, object]],
            ) -> dict[str, list[str]]:
                return {
                    str(machines[0]["name"]): files[:1],
                    str(machines[1]["name"]): files[1:],
                }

        with mock.patch.object(tt, "_load_routing_cfg", return_value={"machines": []}), (
            mock.patch.object(tt, "_load_machine_routing", return_value=FakeRouting())
        ), mock.patch.object(
            tt,
            "_discover_simpletest_files_fast",
            return_value=["apps/a/tests.py", "apps/b/tests.py"],
        ), mock.patch.object(
            tt,
            "_collect_simpletest_files",
            side_effect=AssertionError("dry-run must not use Docker collection"),
        ), mock.patch.object(
            tt.sys,
            "argv",
            ["turbo_tests.py", "--language", "python", "--dry-run"],
        ):
            self.assertEqual(tt.main(), 0)

    def test_dry_run_reports_blocked_remote(self) -> None:
        class FakeRouting:
            class RemoteUnavailableError(RuntimeError):
                pass

            def _select_machines(self, cfg: dict[str, object]) -> list[dict[str, object]]:
                raise self.RemoteUnavailableError("Dell is not reachable")

        with mock.patch.object(tt, "_load_routing_cfg", return_value={"machines": []}), (
            mock.patch.object(tt, "_load_machine_routing", return_value=FakeRouting())
        ), mock.patch.object(
            tt.sys,
            "argv",
            ["turbo_tests.py", "--language", "python", "--dry-run"],
        ):
            self.assertEqual(tt.main(), 1)


class TestConstants(TestCase):
    def test_test_volume_name(self) -> None:
        self.assertEqual(tt._TEST_VOLUME, "xf_test_repo")
