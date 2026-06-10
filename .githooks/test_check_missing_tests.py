"""Tests for the expanded check-missing-tests.py hook.

Covers: Python, Rust, and TypeScript file classification; test candidate
generation; inline #[cfg(test)] detection; glue-file exclusions; and the
OPT_OUT set.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_MOD_PATH = Path(__file__).resolve().parent / "check-missing-tests.py"
_spec = importlib.util.spec_from_file_location("check_missing_tests", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestClassifyFile(unittest.TestCase):
    """classify_file should return the language or None."""

    # --- Python production files ---
    def test_python_service_file(self):
        self.assertEqual(
            mod.classify_file("backend/apps/pipeline/services/scorer.py"),
            "py",
        )

    def test_python_views_file(self):
        self.assertEqual(
            mod.classify_file("backend/apps/pipeline/views.py"),
            "py",
        )

    def test_python_mgmt_command(self):
        path = "backend/apps/auto_issues/management/commands/ingest_foo.py"
        self.assertEqual(mod.classify_file(path), "py")

    def test_python_migration_excluded(self):
        path = "backend/apps/pipeline/migrations/0042_add_field.py"
        self.assertIsNone(mod.classify_file(path))

    def test_python_test_file_excluded(self):
        path = "backend/apps/pipeline/test_scorer.py"
        self.assertIsNone(mod.classify_file(path))

    def test_python_init_excluded(self):
        path = "backend/apps/pipeline/services/__init__.py"
        self.assertIsNone(mod.classify_file(path))

    def test_python_glue_admin(self):
        path = "backend/apps/pipeline/admin.py"
        self.assertIsNone(mod.classify_file(path))

    def test_python_glue_models(self):
        path = "backend/apps/pipeline/models.py"
        self.assertIsNone(mod.classify_file(path))

    def test_python_opt_out(self):
        path = "backend/apps/core/services/settings_base.py"
        self.assertIsNone(mod.classify_file(path))

    # --- Rust production files ---
    def test_rust_production_file(self):
        self.assertEqual(
            mod.classify_file("rust/xf_kernels/src/dedup.rs"),
            "rs",
        )

    def test_rust_test_dir_excluded(self):
        self.assertIsNone(
            mod.classify_file("rust/xf_kernels/src/tests/dedup.rs")
        )

    def test_rust_build_rs_excluded(self):
        self.assertIsNone(
            mod.classify_file("rust/xf_kernels/build.rs")
        )

    def test_rust_lib_rs_excluded(self):
        self.assertIsNone(
            mod.classify_file("rust/xf_kernels/src/lib.rs")
        )

    def test_rust_mod_rs_excluded(self):
        self.assertIsNone(
            mod.classify_file("rust/xf_kernels/src/mod.rs")
        )

    # --- TypeScript production files ---
    def test_ts_component(self):
        self.assertEqual(
            mod.classify_file("frontend/src/app/foo/foo.component.ts"),
            "ts",
        )

    def test_ts_service(self):
        self.assertEqual(
            mod.classify_file("frontend/src/app/core/api.service.ts"),
            "ts",
        )

    def test_ts_spec_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/foo/foo.component.spec.ts")
        )

    def test_ts_stories_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/foo/foo.stories.ts")
        )

    def test_ts_model_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/models/link.model.ts")
        )

    def test_ts_enum_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/enums/status.enum.ts")
        )

    def test_ts_interface_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/interfaces/config.interface.ts")
        )

    def test_ts_dts_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/types/custom.d.ts")
        )

    def test_ts_module_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/app.module.ts")
        )

    def test_ts_routes_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/app.routes.ts")
        )

    def test_ts_index_excluded(self):
        self.assertIsNone(
            mod.classify_file("frontend/src/app/index.ts")
        )

    # --- Non-matching files ---
    def test_markdown_ignored(self):
        self.assertIsNone(mod.classify_file("docs/README.md"))

    def test_json_ignored(self):
        self.assertIsNone(mod.classify_file("config/routing.json"))

    def test_shell_ignored(self):
        self.assertIsNone(mod.classify_file("scripts/run-quality.sh"))


class TestPythonTestCandidates(unittest.TestCase):
    def test_service_file(self):
        path = "backend/apps/pipeline/services/scorer.py"
        candidates = mod.python_test_candidates(path)
        self.assertIn("backend/apps/pipeline/services/test_scorer.py", candidates)
        self.assertIn("backend/apps/pipeline/test_scorer.py", candidates)
        self.assertIn("backend/apps/pipeline/tests/test_scorer.py", candidates)
        self.assertIn("backend/apps/pipeline/tests_scorer.py", candidates)

    def test_mgmt_command(self):
        path = "backend/apps/auto_issues/management/commands/ingest_foo.py"
        candidates = mod.python_test_candidates(path)
        # Should include app-level test paths.
        self.assertIn("backend/apps/auto_issues/test_ingest_foo.py", candidates)
        self.assertIn("backend/apps/auto_issues/tests_ingest_foo.py", candidates)


class TestRustTestCandidates(unittest.TestCase):
    def test_rust_file(self):
        path = "rust/xf_kernels/src/dedup.rs"
        candidates = mod.rust_test_candidates(path)
        self.assertIn("rust/xf_kernels/src/tests/dedup.rs", candidates)


class TestTsTestCandidates(unittest.TestCase):
    def test_component(self):
        path = "frontend/src/app/foo/foo.component.ts"
        candidates = mod.ts_test_candidates(path)
        self.assertEqual(
            candidates, ["frontend/src/app/foo/foo.component.spec.ts"]
        )


class TestRustInlineTests(unittest.TestCase):
    def test_file_with_cfg_test(self):
        with tempfile.NamedTemporaryFile(
            suffix=".rs", mode="w", delete=False
        ) as f:
            f.write('fn main() {}\n\n#[cfg(test)]\nmod tests {\n}\n')
            f.flush()
            # Patch REPO_ROOT so the function finds our temp file.
            rel = os.path.basename(f.name)
            tmpdir = Path(os.path.dirname(f.name))
            with patch.object(mod, "REPO_ROOT", tmpdir):
                self.assertTrue(mod.rust_has_inline_tests(rel))
        os.unlink(f.name)

    def test_file_without_cfg_test(self):
        with tempfile.NamedTemporaryFile(
            suffix=".rs", mode="w", delete=False
        ) as f:
            f.write("fn main() {}\n")
            f.flush()
            rel = os.path.basename(f.name)
            tmpdir = Path(os.path.dirname(f.name))
            with patch.object(mod, "REPO_ROOT", tmpdir):
                self.assertFalse(mod.rust_has_inline_tests(rel))
        os.unlink(f.name)


class TestFileExistsAnywhere(unittest.TestCase):
    def test_staged_match(self):
        staged = {"backend/apps/core/test_foo.py"}
        self.assertTrue(
            mod.file_exists_anywhere(["backend/apps/core/test_foo.py"], staged)
        )

    def test_no_match(self):
        staged = set()
        self.assertFalse(
            mod.file_exists_anywhere(["nonexistent/test_bar.py"], staged)
        )


class TestScriptsPattern(unittest.TestCase):
    def test_scripts_py_classified(self):
        self.assertEqual(
            mod.classify_file("scripts/machine_routing.py"), "py"
        )

    def test_githook_py_classified(self):
        self.assertEqual(
            mod.classify_file(".githooks/check-debug-code.py"), "py"
        )

    def test_scripts_test_excluded(self):
        self.assertIsNone(
            mod.classify_file("scripts/test_machine_routing.py")
        )

    def test_githook_test_excluded(self):
        self.assertIsNone(
            mod.classify_file(".githooks/test_check_debug_code.py")
        )


if __name__ == "__main__":
    unittest.main()
