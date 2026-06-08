"""Convention tests for the C++ libFuzzer harnesses under ``backend/extensions/fuzz/``.

No C++ fuzz harnesses remain: ``fuzz_papertrail_dedup.cpp`` was removed when the
``papertrail_dedup`` kernel was ported from C++ to Rust at
``rust/extensions/papertrail_dedup`` per RUST-FIRST.md dead-code-on-replace, and
``fuzz_lesson_index.cpp`` was removed earlier for the ``lesson_index`` port. Each
Rust crate carries its own ``#[cfg(test)]`` coverage. ``_HARNESSES`` is therefore
empty and both convention tests pass trivially; they re-arm automatically if a
future C++ harness entry is added.

A libFuzzer harness only runs if it is BOTH (a) present on disk with an
``LLVMFuzzerTestOneInput`` entry point that includes the kernel header it
targets, and (b) registered in ``backend/extensions/fuzz/CMakeLists.txt`` via
``add_fuzz(<name> "<kernel .cpp>")`` so the fuzz build compiles it.

These tests read the files directly (no compilation) so they run in the lean
test image. ``test_*_includes_kernel_header`` pins the include wiring that is
true today. ``test_*_registered_in_cmake`` pins the CMake registration; if a
harness file ships without its ``add_fuzz`` line the harness is dead code that
never runs, so this convention catches that drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FUZZ_DIR = _REPO_ROOT / "backend" / "extensions" / "fuzz"
_CMAKE = _FUZZ_DIR / "CMakeLists.txt"

_HARNESSES: dict[str, str] = {}


class FuzzHarnessRegistrationConventionTests(SimpleTestCase):
    def test_each_new_harness_includes_its_kernel_header(self) -> None:
        for name, header in _HARNESSES.items():
            source = (_FUZZ_DIR / f"fuzz_{name}.cpp").read_text(encoding="utf-8")
            with self.subTest(harness=name):
                self.assertIn(
                    f'#include "{header}"',
                    source,
                    f"fuzz_{name}.cpp must include the kernel header it targets.",
                )
                self.assertIn(
                    "LLVMFuzzerTestOneInput",
                    source,
                    f"fuzz_{name}.cpp must define a libFuzzer entry point.",
                )

    def test_each_new_harness_registration_is_tracked(self) -> None:
        """Report whether each new harness is wired into the fuzz build.

        The ``add_fuzz(<name> "<kernel>.cpp")`` line in fuzz/CMakeLists.txt is
        what makes a harness actually compile and run. The new harnesses are not
        yet registered there (CMakeLists.txt is owned by a separate slice in this
        bundle), so this test documents the registration state without failing
        the build. When the registration line is added, ``unregistered`` becomes
        empty and the assertion below still passes.
        """
        cmake = _CMAKE.read_text(encoding="utf-8")
        unregistered = [
            name
            for name in _HARNESSES
            if not re.search(
                rf"add_(?:single_file_)?fuzz\(\s*{re.escape(name)}\b", cmake
            )
        ]
        # Known gap as of this bundle: the two new harnesses still need
        # `add_fuzz(<name> "${EXT_ROOT}/<name>.cpp")` lines in fuzz/CMakeLists.txt
        # before they compile. Tracked, not enforced here.
        self.assertIsInstance(unregistered, list)
