"""Tests for scripts/detect_changed_modules.py (Phase J + K2).

Drives `_classify` and `_classify_by_module` against synthetic file
lists. No git dependency, no I/O beyond reading coverage-modules.yaml
(which already exists in the repo).
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load():
    path = SCRIPTS_DIR / "detect_changed_modules.py"
    spec = importlib.util.spec_from_file_location("detect_changed_modules", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["detect_changed_modules"] = module
    spec.loader.exec_module(module)
    return module


m = _load()


class ClassifyByLanguageTests(unittest.TestCase):
    """`_classify` groups changed files by language."""

    def test_angular_components_recognised(self):
        files = ["frontend/src/app/foo/foo.component.ts"]
        b = m._classify(files)
        self.assertEqual(b["angular"], ["frontend/src/app/foo/foo.component.ts"])

    def test_angular_services_recognised(self):
        files = ["frontend/src/app/foo/foo.service.ts"]
        b = m._classify(files)
        self.assertEqual(b["angular"], ["frontend/src/app/foo/foo.service.ts"])

    def test_angular_spec_files_excluded(self):
        files = ["frontend/src/app/foo/foo.component.spec.ts"]
        b = m._classify(files)
        self.assertEqual(b["angular"], [])

    def test_python_apps_recognised(self):
        files = ["backend/apps/audit/services.py"]
        b = m._classify(files)
        self.assertEqual(b["python"], ["backend/apps/audit/services.py"])

    def test_python_tests_excluded(self):
        files = ["backend/apps/foo/tests/test_x.py", "backend/apps/foo/test_y.py"]
        b = m._classify(files)
        self.assertEqual(b["python"], [])

    def test_python_init_files_excluded(self):
        files = ["backend/apps/foo/__init__.py"]
        b = m._classify(files)
        self.assertEqual(b["python"], [])

    def test_go_modules_recognised(self):
        files = ["services/streamd/internal/foo.go"]
        b = m._classify(files)
        self.assertEqual(b["go"], ["services/streamd/internal/foo.go"])

    def test_go_test_files_excluded(self):
        files = ["services/streamd/internal/foo_test.go"]
        b = m._classify(files)
        self.assertEqual(b["go"], [])

    def test_cpp_extensions_recognised(self):
        files = ["backend/extensions/scoring.cpp",
                 "backend/extensions/include/util.h"]
        b = m._classify(files)
        self.assertEqual(len(b["cpp"]), 2)

    def test_cpp_test_files_excluded(self):
        files = ["backend/extensions/tests/test_scoring.cpp"]
        b = m._classify(files)
        self.assertEqual(b["cpp"], [])

    def test_unmatched_file_falls_through(self):
        files = ["docs/README.md", "config/foo.json"]
        b = m._classify(files)
        for bucket in b.values():
            self.assertEqual(bucket, [])


class ClassifyByModuleTests(unittest.TestCase):
    """`_classify_by_module` reads coverage-modules.yaml and groups by module."""

    def test_audit_file_maps_to_governance(self):
        # backend/apps/audit/**/*.py is in `governance` tier1.
        files = ["backend/apps/audit/services.py"]
        modules = m._classify_by_module(files)
        self.assertIn("governance", modules)
        self.assertIn("backend/apps/audit/services.py", modules["governance"])

    def test_cpp_extension_maps_to_cpp_module(self):
        files = ["backend/extensions/scoring.cpp"]
        modules = m._classify_by_module(files)
        self.assertIn("cpp_extensions", modules)

    def test_streamd_go_maps_to_streamd_module(self):
        files = ["services/streamd/internal/foo.go"]
        modules = m._classify_by_module(files)
        self.assertIn("streamd", modules)

    def test_angular_component_maps_to_angular_components(self):
        files = ["frontend/src/app/foo/foo.component.ts"]
        modules = m._classify_by_module(files)
        self.assertIn("angular_components", modules)

    def test_no_modules_when_files_dont_match(self):
        files = ["docs/README.md"]
        modules = m._classify_by_module(files)
        self.assertEqual(modules, {})


class GlobMatchingTests(unittest.TestCase):
    """`_match_glob` handles `**` for recursive globs."""

    def test_recursive_glob_matches_nested(self):
        self.assertTrue(m._match_glob(
            "backend/apps/audit/**/*.py",
            "backend/apps/audit/services/foo.py",
        ))

    def test_recursive_glob_matches_top_level(self):
        self.assertTrue(m._match_glob(
            "backend/apps/audit/**/*.py",
            "backend/apps/audit/models.py",
        ))

    def test_non_recursive_glob_does_not_descend(self):
        # `backend/apps/*/services/scoring.py` should match
        # `backend/apps/foo/services/scoring.py` but NOT
        # `backend/apps/foo/services/sub/scoring.py`.
        self.assertTrue(m._match_glob(
            "backend/apps/*/services/scoring.py",
            "backend/apps/foo/services/scoring.py",
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
