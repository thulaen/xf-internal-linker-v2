"""Tests for .githooks/check-no-cross-language-import.py (slice 1.5).

Focused cases:
  (a) clean Python (no flags)
  (b) Python with `import ctypes` + `ctypes.CDLL(...)` of a services/ path
  (c) Python with `subprocess.run(...)` of a services/ binary

The hook is tested via its `scan_paths()` helper so the test does not depend
on a real git index. The hook itself reads staged files via git in main().
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    """Load the hyphenated hook module by spec so we can import its helpers.

    The module is registered in sys.modules before exec_module so that
    @dataclass decorators inside the hook can resolve cls.__module__.
    """
    module_name = "check_no_cross_language_import"
    hook_path = HOOKS_DIR / "check-no-cross-language-import.py"
    spec = importlib.util.spec_from_file_location(module_name, hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class CrossLanguageImportHookTests(TestCase):

    def _write(self, root: Path, rel: str, body: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_clean_python_has_no_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/something/handler.py",
                "from apps.realtime.api import broadcast\n"
                "\n"
                "def handle(event):\n"
                "    broadcast('topic', 'event', event)\n",
            )
            violations = hook.scan_paths([py])
            self.assertEqual(violations, [],
                             f"clean files should not raise violations: {violations}")

    def test_python_ctypes_cdll_into_services_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/bad_client.py",
                "import ctypes\n"
                "\n"
                "lib = ctypes.CDLL('./services/streamd/streamd.so')\n"
                "lib.publish(b'payload')\n",
            )
            violations = hook.scan_paths([py])
            self.assertGreaterEqual(
                len(violations), 1,
                "ctypes.CDLL into services/ must be flagged",
            )
            self.assertTrue(
                any("ctypes" in v.rule.lower() or "CDLL" in v.snippet for v in violations),
                f"violation should mention ctypes/CDLL; got {violations}",
            )

    def test_python_subprocess_into_services_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/bad_subprocess.py",
                "import subprocess\n"
                "\n"
                "def call_streamd():\n"
                "    subprocess.run(['./services/streamd/streamd', 'publish'])\n",
            )
            violations = hook.scan_paths([py])
            self.assertGreaterEqual(
                len(violations), 1,
                "subprocess.run into services/ must be flagged",
            )
            self.assertTrue(
                any("subprocess" in v.rule.lower() for v in violations),
                f"violation should mention subprocess; got {violations}",
            )

class CrossLanguageImportHookEdgeCases(TestCase):
    """Additional cases for full coverage of the hook surface."""

    def _write(self, root: Path, rel: str, body: str) -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_python_cdll_loadlibrary_into_services_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/lib_load.py",
                "import ctypes\n"
                "\n"
                "ctypes.cdll.LoadLibrary('./services/streamd/streamd.so')\n",
            )
            violations = hook.scan_paths([py])
            self.assertTrue(
                any("ctypes" in v.rule.lower() for v in violations),
                f"ctypes.cdll.LoadLibrary should be flagged; got {violations}",
            )

    def test_python_os_system_into_services_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/bad_system.py",
                "import os\n"
                "\n"
                "os.system('./services/streamd/streamd publish')\n",
            )
            violations = hook.scan_paths([py])
            self.assertTrue(
                any("os.system" in v.rule for v in violations),
                f"os.system should be flagged; got {violations}",
            )

    def test_python_subprocess_kwarg_args_into_services_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/bad_kwarg.py",
                "import subprocess\n"
                "\n"
                "subprocess.run(args='./services/streamd/streamd')\n",
            )
            violations = hook.scan_paths([py])
            self.assertTrue(
                any("subprocess" in v.rule.lower() for v in violations),
                f"subprocess(args=...) should be flagged; got {violations}",
            )

    def test_python_with_syntax_error_is_skipped_silently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/broken.py",
                "import ctypes\n"
                "ctypes.CDLL(  # unclosed paren\n",
            )
            violations = hook.scan_paths([py])
            self.assertEqual(violations, [], "syntax errors must be tolerated")

    def test_python_subprocess_without_services_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/safe_subprocess.py",
                "import subprocess\n"
                "\n"
                "subprocess.run(['echo', 'hello'])\n",
            )
            self.assertEqual(hook.scan_paths([py]), [])

    def test_unknown_suffix_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md = self._write(
                root,
                "README.md",
                "subprocess.run(['./services/streamd/streamd'])\n",
            )
            self.assertEqual(hook.scan_paths([md]), [])

    def test_missing_path_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(hook.scan_paths([root / "missing.py"]), [])

    def test_format_failure_includes_three_part_message(self) -> None:
        v = hook.Violation(
            path=Path("backend/apps/realtime/bad.py"),
            line=42,
            snippet="ctypes.CDLL('./services/streamd/streamd.so')",
            rule="ctypes.CDLL into services/",
        )
        text = hook._format_failure([v])
        self.assertIn("FAIL check-no-cross-language-import", text)
        self.assertIn("WHY:", text)
        self.assertIn("UNBLOCK:", text)
        self.assertIn("ADR 0006", text)
        self.assertIn("api.proto", text)
        self.assertIn("apps.realtime._streamd_client", text)
        self.assertIn("bad.py:42", text)
        self.assertIn("report_hook_false_positive", text)

    def test_main_returns_zero_when_no_staged_files(self) -> None:
        # Stub the staged-file reader so the test never touches the real git index.
        original = hook._staged_files
        try:
            hook._staged_files = lambda: []  # type: ignore[assignment]
            self.assertEqual(hook.main(), 0)
        finally:
            hook._staged_files = original  # type: ignore[assignment]

    def test_main_returns_two_on_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/main_bad.py",
                "import ctypes\n"
                "ctypes.CDLL('./services/streamd/streamd.so')\n",
            )
            original = hook._staged_files
            try:
                hook._staged_files = lambda: [py]  # type: ignore[assignment]
                self.assertEqual(hook.main(), 2)
            finally:
                hook._staged_files = original  # type: ignore[assignment]

    def test_staged_files_returns_empty_when_git_missing(self) -> None:
        # Patch subprocess.run inside the hook module to raise FileNotFoundError.
        import subprocess as _sp
        original = _sp.run

        def _fake_run(*args, **kwargs):
            raise FileNotFoundError("git not available in test env")

        try:
            _sp.run = _fake_run  # type: ignore[assignment]
            self.assertEqual(hook._staged_files(), [])
        finally:
            _sp.run = original  # type: ignore[assignment]

    def test_staged_files_parses_git_output(self) -> None:
        """Hit the happy path of _staged_files() with a stubbed git result.

        Only .py paths are collected now; the .go and .md lines must be
        filtered out.
        """
        import subprocess as _sp
        original = _sp.run

        class _Result:
            stdout = "backend/apps/realtime/x.py\nservices/streamd/y.go\nREADME.md\n\n"
            returncode = 0

        def _fake_run(*args, **kwargs):
            return _Result()

        try:
            _sp.run = _fake_run  # type: ignore[assignment]
            paths = hook._staged_files()
        finally:
            _sp.run = original  # type: ignore[assignment]
        suffixes = sorted(p.suffix for p in paths)
        self.assertEqual(suffixes, [".py"], f"got {paths}")

    def test_non_string_arg_does_not_crash_scan(self) -> None:
        """`subprocess.run(args=42)` exercises the non-string branch in _check_const."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py = self._write(
                root,
                "backend/apps/realtime/numeric_arg.py",
                "import subprocess\n"
                "\n"
                "subprocess.run(42, executable=None)\n",
            )
            # No exception, no false positive.
            self.assertEqual(hook.scan_paths([py]), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
