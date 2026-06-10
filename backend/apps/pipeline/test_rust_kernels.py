"""Tests for the shared Rust-kernel loader (RUST-FIRST.md, zero fallback).

Given the backend has many hot paths owned by Rust kernels (PyO3 modules under
``extensions.<name>``), When more than one Python module needs to "import the
Rust kernel or fail loudly", Then that logic must live in exactly one place so
every caller raises the same loud, actionable error instead of silently
dropping to a slower Python path.
"""

from __future__ import annotations

import sys
import types

from django.test import SimpleTestCase

from apps.pipeline.services.rust_kernels import KernelUnavailableError, load_kernel


class LoadKernelTests(SimpleTestCase):
    """Behaviour of ``load_kernel(module_name, attr_name)``."""

    def setUp(self) -> None:
        # Track injected fake modules so tearDown can remove them and never
        # leak a fake ``extensions.<x>`` into other tests.
        self._injected: list[str] = []
        self.addCleanup(self._remove_injected)

    def _inject(self, fullname: str, module: types.ModuleType | None) -> None:
        if module is None:
            sys.modules.pop(fullname, None)
        else:
            sys.modules[fullname] = module
        self._injected.append(fullname)

    def _remove_injected(self) -> None:
        for name in self._injected:
            sys.modules.pop(name, None)

    def test_returns_module_when_kernel_and_attr_present(self) -> None:
        fake = types.ModuleType("extensions.fake_kernel")
        fake.do_thing = lambda value: value * 2  # type: ignore[attr-defined]
        self._inject("extensions.fake_kernel", fake)

        loaded = load_kernel("extensions.fake_kernel", "do_thing")

        self.assertIs(loaded, fake)
        self.assertEqual(loaded.do_thing(21), 42)

    def test_raises_loud_error_when_module_missing(self) -> None:
        # No such module is importable -> a loud KernelUnavailableError, never
        # a silent None and never a swallowed ImportError.
        with self.assertRaises(KernelUnavailableError) as ctx:
            load_kernel("extensions.definitely_not_built", "normalize")

        message = str(ctx.exception)
        self.assertIn("extensions.definitely_not_built", message)
        self.assertIn("no Python fallback", message)
        self.assertIn("ensure_compiled_artifacts", message)

    def test_raises_loud_error_when_attr_missing(self) -> None:
        fake = types.ModuleType("extensions.partial_kernel")
        # Module imports but the required public attribute is absent.
        self._inject("extensions.partial_kernel", fake)

        with self.assertRaises(KernelUnavailableError) as ctx:
            load_kernel("extensions.partial_kernel", "missing_fn")

        message = str(ctx.exception)
        self.assertIn("missing_fn", message)
        self.assertIn("extensions.partial_kernel", message)

    def test_error_is_a_runtime_error_subclass(self) -> None:
        # Callers that already catch RuntimeError (the pre-refactor contract in
        # embeddings.py / anchor_garbage_signals.py) keep working.
        self.assertTrue(issubclass(KernelUnavailableError, RuntimeError))
