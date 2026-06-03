"""Tests for scripts/select_python_test_targets.py refactored helpers.

BDD:
  Given a backend-relative module path
  When _module_needles() runs
  Then it returns the dotted module plus the apps-normalised form

  Given a path whose first part is "config"
  When _candidate_tests_for_path() runs
  Then it returns the two config test candidates

These pin the helpers extracted during the 2026-06 refactor so a mutation
of the string-building logic is caught.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "select_python_test_targets.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "select_python_test_targets", _MODULE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_python_test_targets"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


class TestBackendRoot(TestCase):
    def test_appends_backend(self) -> None:
        self.assertEqual(m._backend_root(Path("/repo")), Path("/repo/backend"))


class TestModuleNeedles(TestCase):
    def test_apps_module_dedupes_to_two(self) -> None:
        needles = m._module_needles(Path("apps/audit/models.py"))
        self.assertEqual(needles, {"apps.audit.models"})

    def test_non_apps_module_adds_apps_prefix(self) -> None:
        needles = m._module_needles(Path("config/settings.py"))
        self.assertEqual(needles, {"config.settings", "apps.config.settings"})

    def test_services_path_adds_bare_stem(self) -> None:
        needles = m._module_needles(Path("apps/services/streamd/client.py"))
        self.assertIn("client", needles)
        self.assertIn("apps.services.streamd.client", needles)

    def test_non_services_path_omits_bare_stem(self) -> None:
        needles = m._module_needles(Path("apps/audit/models.py"))
        self.assertNotIn("models", needles)


class TestReadText(TestCase):
    def test_returns_text(self) -> None:
        path = mock.Mock()
        path.read_text.return_value = "hello"
        self.assertEqual(m._read_text(path), "hello")

    def test_returns_empty_on_unicode_error(self) -> None:
        path = mock.Mock()
        path.read_text.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "boom")
        self.assertEqual(m._read_text(path), "")


class TestCandidateTestsForPath(TestCase):
    def test_config_returns_two_candidates(self) -> None:
        result = m._candidate_tests_for_path(Path("/repo"), Path("config/urls.py"))
        self.assertEqual(
            result, [Path("config") / "tests.py", Path("config") / "tests"]
        )

    def test_test_path_returns_itself(self) -> None:
        rel = Path("apps/audit/tests/test_x.py")
        self.assertEqual(m._candidate_tests_for_path(Path("/repo"), rel), [rel])

    def test_falls_back_to_existing_candidates(self) -> None:
        rel = Path("apps/audit/models.py")
        with mock.patch.object(
            m, "_generated_sidecar_contract_tests", return_value=[]
        ), mock.patch.object(
            m, "_existing_candidates", return_value=[Path("sentinel.py")]
        ) as existing:
            result = m._candidate_tests_for_path(Path("/repo"), rel)
        existing.assert_called_once()
        self.assertEqual(result, [Path("sentinel.py")])


class TestSameAppSearchRoot(TestCase):
    def test_none_when_not_apps(self) -> None:
        self.assertIsNone(
            m._same_app_search_root(Path("/repo"), Path("config/urls.py"))
        )

    def test_none_when_dir_missing(self) -> None:
        with mock.patch.object(m.Path, "is_dir", return_value=False):
            self.assertIsNone(
                m._same_app_search_root(Path("/repo"), Path("apps/audit/models.py"))
            )

    def test_returns_search_root_when_dir_exists(self) -> None:
        with mock.patch.object(m.Path, "is_dir", return_value=True):
            result = m._same_app_search_root(
                Path("/repo"), Path("apps/audit/models.py")
            )
        self.assertEqual(result, Path("/repo/backend/apps/audit"))
