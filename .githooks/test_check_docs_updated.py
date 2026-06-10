#!/usr/bin/env python3
"""Unit tests for check-docs-updated.py."""
import importlib.util
import os
import sys
import unittest

# Import the hook module by file path
_hook_path = os.path.join(
    os.path.dirname(__file__), "check-docs-updated.py"
)
_spec = importlib.util.spec_from_file_location("check_docs_updated", _hook_path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestIsSourceFile(unittest.TestCase):
    def test_backend_py(self):
        self.assertTrue(mod.is_source_file("backend/apps/pipeline/views.py"))

    def test_frontend_ts(self):
        self.assertTrue(mod.is_source_file("frontend/src/app/app.component.ts"))

    def test_rust_rs(self):
        self.assertTrue(mod.is_source_file("rust/kernels/src/lib.rs"))

    def test_scripts_sh(self):
        self.assertTrue(mod.is_source_file("scripts/run-tests.sh"))

    def test_docs_not_source(self):
        self.assertFalse(mod.is_source_file("docs/TESTING.md"))

    def test_root_file_not_source(self):
        self.assertFalse(mod.is_source_file("README.md"))

    def test_githooks_not_source(self):
        self.assertFalse(mod.is_source_file(".githooks/check-docs-updated.py"))


class TestIsExempt(unittest.TestCase):
    def test_test_file_python(self):
        self.assertTrue(mod.is_exempt("backend/apps/pipeline/test_views.py"))

    def test_test_file_ts(self):
        self.assertTrue(mod.is_exempt("frontend/src/app/app.component.spec.ts"))

    def test_conftest(self):
        self.assertTrue(mod.is_exempt("backend/conftest.py"))

    def test_tests_dir(self):
        self.assertTrue(mod.is_exempt("backend/tests/test_api.py"))

    def test_migration(self):
        self.assertTrue(mod.is_exempt("backend/apps/content/migrations/0001_initial.py"))

    def test_env_file(self):
        self.assertTrue(mod.is_exempt(".env.production"))

    def test_yaml_file(self):
        self.assertTrue(mod.is_exempt("docker-compose.yml"))

    def test_github_workflow(self):
        self.assertTrue(mod.is_exempt(".github/workflows/ci.yml"))

    def test_agent_handoff(self):
        self.assertTrue(mod.is_exempt("AGENT-HANDOFF.md"))

    def test_githook(self):
        self.assertTrue(mod.is_exempt(".githooks/check-missing-tests.py"))

    def test_docs_dir(self):
        self.assertTrue(mod.is_exempt("docs/TESTING.md"))

    def test_docs_site_dir(self):
        self.assertTrue(mod.is_exempt("docs-site/docs/intro.md"))

    def test_lock_file(self):
        self.assertTrue(mod.is_exempt("frontend/package-lock.json"))

    def test_production_py_not_exempt(self):
        self.assertFalse(mod.is_exempt("backend/apps/pipeline/services/engine.py"))

    def test_production_ts_not_exempt(self):
        self.assertFalse(mod.is_exempt("frontend/src/app/services/api.service.ts"))


class TestIsDocsFile(unittest.TestCase):
    def test_docs_site_page(self):
        self.assertTrue(mod.is_docs_file("docs-site/docs/intro.md"))

    def test_docs_site_css(self):
        self.assertTrue(mod.is_docs_file("docs-site/src/css/custom.css"))

    def test_raw_docs_not_docs_site(self):
        self.assertFalse(mod.is_docs_file("docs/TESTING.md"))

    def test_backend_not_docs(self):
        self.assertFalse(mod.is_docs_file("backend/apps/pipeline/views.py"))


if __name__ == "__main__":
    unittest.main()
