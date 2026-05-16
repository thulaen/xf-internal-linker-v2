"""Smoke tests for the 4 lifecycle-helper management commands added 2026-05-16.

Each test invokes the command via `call_command` and asserts that the command
runs to completion without raising. The commands themselves do read-only work
(audit_*) or write to user-supplied paths (scaffold_*) that the smoke tests
keep inside a temporary directory via the REPO_ROOT environment variable.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from django.core.management import call_command


_FAKE_ENSURE = (
    "EXTENSION_NAMES = {\n"
    '    "alpha",\n'
    '    "beta",\n'
    "}\n"
)

_FAKE_HEALTH = (
    "_NATIVE_RUNTIME_MODULES = (\n"
    '    ("alpha", "ping_alpha", "alpha kernel", False),\n'
    '    ("beta", "ping_beta", "beta kernel", False),\n'
    ")\n"
)

_GOOD_PYBIND = (
    "#include <pybind11/pybind11.h>\n"
    "PYBIND11_MODULE(alpha, m) {{ m.doc() = \"alpha\"; }}\n"
)

_GOOD_PYBIND_BETA = (
    "#include <pybind11/pybind11.h>\n"
    "PYBIND11_MODULE(beta, m) {{ m.doc() = \"beta\"; }}\n"
)


def _make_repo(tmp: Path) -> None:
    (tmp / ".githooks").mkdir()
    (tmp / "backend" / "extensions").mkdir(parents=True)
    (tmp / "scripts").mkdir()
    (tmp / "backend" / "apps" / "diagnostics").mkdir(parents=True)
    (tmp / "backend" / "extensions" / "alpha.cpp").write_text(_GOOD_PYBIND, encoding="utf-8")
    (tmp / "backend" / "extensions" / "beta.cpp").write_text(_GOOD_PYBIND_BETA, encoding="utf-8")
    (tmp / "scripts" / "ensure_compiled_artifacts.py").write_text(_FAKE_ENSURE, encoding="utf-8")
    (tmp / "backend" / "apps" / "diagnostics" / "health.py").write_text(_FAKE_HEALTH, encoding="utf-8")
    (tmp / "services").mkdir()


class AuditCppLifecycleSmokeTests(TestCase):

    def test_audit_runs_and_reports_two_present_kernels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command("audit_cpp_lifecycle", stdout=out)
                output = out.getvalue()
            self.assertIn("PRESENT (all three places): 2", output)
            self.assertIn("BROKEN", output)

    def test_audit_only_broken_filters_out_present_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command("audit_cpp_lifecycle", "--only-broken", stdout=out)
                output = out.getvalue()
            self.assertIn("BROKEN  (half-registered or 0-byte): 0", output)


class AuditGoServicesSmokeTests(TestCase):

    def test_audit_runs_with_empty_services_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            # The audit command imports the hook script from .githooks/; copy the
            # real hook there so the synthetic repo is self-sufficient.
            hooks_dir = tmp / ".githooks"
            real_hook = Path("/repo/.githooks/check-go-service-contract.py")
            if real_hook.is_file():
                (hooks_dir / "check-go-service-contract.py").write_text(
                    real_hook.read_text(encoding="utf-8"), encoding="utf-8"
                )
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                err = io.StringIO()
                call_command("audit_go_services", stdout=out, stderr=err)
                output = out.getvalue() + err.getvalue()
            # Either "audit started" or "no services" message is acceptable.
            self.assertTrue(
                "Go service lifecycle audit" in output or "no services/ directory" in output,
                f"unexpected output: {output!r}",
            )


class ScaffoldCppKernelSmokeTests(TestCase):

    def test_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command(
                    "scaffold_cpp_kernel",
                    "--name", "smoke_kernel",
                    "--callable", "ping",
                    "--description", "smoke",
                    "--dry-run",
                    stdout=out,
                )
                output = out.getvalue()
            self.assertIn("Dry-run only", output)
            self.assertFalse((tmp / "backend" / "extensions" / "smoke_kernel.cpp").exists())

    def test_real_run_creates_cpp_file_and_edits_registrations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command(
                    "scaffold_cpp_kernel",
                    "--name", "smoke_kernel",
                    "--callable", "ping",
                    "--description", "smoke",
                    stdout=out,
                )
            cpp_path = tmp / "backend" / "extensions" / "smoke_kernel.cpp"
            self.assertTrue(cpp_path.is_file())
            cpp_text = cpp_path.read_text(encoding="utf-8")
            self.assertIn("PYBIND11_MODULE(smoke_kernel", cpp_text)
            ensure_text = (tmp / "scripts" / "ensure_compiled_artifacts.py").read_text(encoding="utf-8")
            self.assertIn('"smoke_kernel"', ensure_text)
            health_text = (tmp / "backend" / "apps" / "diagnostics" / "health.py").read_text(encoding="utf-8")
            self.assertIn('"smoke_kernel"', health_text)


class ScaffoldGoServiceSmokeTests(TestCase):

    def test_dry_run_lists_planned_files_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command(
                    "scaffold_go_service",
                    "--name", "smokesvc",
                    "--description", "smoke",
                    "--dry-run",
                    stdout=out,
                )
                output = out.getvalue()
            self.assertIn("would create services/smokesvc/go.mod", output)
            self.assertIn("smokesvc_sock", output)
            self.assertFalse((tmp / "services" / "smokesvc").exists())

    def test_real_run_creates_service_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _make_repo(tmp)
            with patch.dict(os.environ, {"REPO_ROOT": str(tmp)}):
                out = io.StringIO()
                call_command(
                    "scaffold_go_service",
                    "--name", "smokesvc",
                    "--description", "smoke",
                    stdout=out,
                )
            folder = tmp / "services" / "smokesvc"
            self.assertTrue((folder / "go.mod").is_file())
            self.assertTrue((folder / "api.proto").is_file())
            self.assertTrue((folder / "cmd" / "smokesvc" / "main.go").is_file())
            self.assertTrue((folder / "Dockerfile").is_file())
            self.assertTrue((folder / "api" / "gen" / "api.pb.go").is_file())
