"""Tests for .githooks/check-go-service-contract.py (slice 1.5).

Each services/<name>/ folder must publish BOTH:
  - one of api.proto or api.http.md (the public RPC contract)
  - cmd/<name>/main.go (the binary entry point — closes the library-only loophole)

Test cases (5):
  (a) contract + binary both present (clean)
  (b) contract missing, binary present
  (c) binary missing, contract present (library-only loophole)
  (d) both missing
  (e) services dir empty / does not exist
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
    module_name = "check_go_service_contract"
    hook_path = HOOKS_DIR / "check-go-service-contract.py"
    spec = importlib.util.spec_from_file_location(module_name, hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _make_service(
    base: Path,
    name: str,
    with_contract: bool = True,
    with_binary: bool = True,
) -> Path:
    folder = base / "services" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "go.mod").write_text(
        f"module xf-internal-linker-v2/services/{name}\n\ngo 1.25\n",
        encoding="utf-8",
    )
    if with_contract:
        proto = folder / "api.proto"
        proto.write_text(
            f"syntax = \"proto3\";\npackage xf.{name}.v1;\n", encoding="utf-8"
        )
    if with_binary:
        bin_path = folder / "cmd" / name / "main.go"
        bin_path.parent.mkdir(parents=True, exist_ok=True)
        bin_path.write_text(
            "package main\nfunc main() {}\n", encoding="utf-8"
        )
    return folder


class ContractPresenceHookTests(TestCase):

    def test_clean_service_with_contract_and_binary_has_no_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            folder = _make_service(base, "streamd")
            self.assertEqual(hook.scan_service_folder(folder), [])

    def test_missing_contract_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            folder = _make_service(base, "streamd", with_contract=False)
            violations = hook.scan_service_folder(folder)
            self.assertEqual(len(violations), 1)
            v = violations[0]
            self.assertIn("api.proto", v.message)
            self.assertIn("api.http.md", v.message)

    def test_missing_binary_is_the_library_only_loophole(self) -> None:
        """A services/<name>/ folder must NOT be allowed as a library-only Go
        module — the binary entry point is the speed-claim guarantee."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            folder = _make_service(base, "streamd", with_binary=False)
            violations = hook.scan_service_folder(folder)
            self.assertEqual(len(violations), 1)
            v = violations[0]
            self.assertIn("cmd/streamd/main.go", v.message)
            self.assertIn("library-only", v.message.lower())

    def test_both_missing_is_two_violations_naming_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            folder = _make_service(
                base, "streamd", with_contract=False, with_binary=False
            )
            violations = hook.scan_service_folder(folder)
            self.assertEqual(len(violations), 2)
            joined = " | ".join(v.message for v in violations)
            self.assertIn("api.proto", joined)
            self.assertIn("cmd/streamd/main.go", joined)

    def test_empty_services_dir_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "services").mkdir()
            self.assertEqual(hook.scan_base_dir(base), [])

    def test_missing_services_dir_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # No services/ folder at all.
            self.assertEqual(hook.scan_base_dir(base), [])

    def test_scan_base_dir_aggregates_violations_across_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _make_service(base, "streamd")  # clean
            _make_service(base, "webhookd", with_contract=False)  # 1 violation
            _make_service(
                base, "crawld", with_contract=False, with_binary=False
            )  # 2 violations
            violations = hook.scan_base_dir(base)
            self.assertEqual(len(violations), 3)

    def test_format_failure_includes_three_part_message(self) -> None:
        v = hook.Violation(
            service="streamd",
            kind="contract",
            message="services/streamd/ is missing both api.proto and api.http.md",
        )
        text = hook._format_failure([v])
        self.assertIn("FAIL check-go-service-contract", text)
        self.assertIn("WHY:", text)
        self.assertIn("UNBLOCK:", text)
        self.assertIn("ADR 0006", text)
        self.assertIn("library-only", text.lower())

    def test_main_returns_zero_when_no_services_folder(self) -> None:
        original = hook.SERVICES_DIR
        try:
            # Point at a non-existent path so main() finds nothing.
            with tempfile.TemporaryDirectory() as tmp:
                hook.SERVICES_DIR = Path(tmp) / "no-such-services"  # type: ignore[assignment]
                self.assertEqual(hook.main(), 0)
        finally:
            hook.SERVICES_DIR = original  # type: ignore[assignment]

    def test_main_returns_two_on_violations(self) -> None:
        original = hook.SERVICES_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                _make_service(base, "broken", with_contract=False, with_binary=False)
                hook.SERVICES_DIR = base / "services"  # type: ignore[assignment]
                self.assertEqual(hook.main(), 2)
        finally:
            hook.SERVICES_DIR = original  # type: ignore[assignment]


if __name__ == "__main__":
    import unittest

    unittest.main()
