"""Tests for scripts/cpp_mutation_targets.py (Phase K1).

Synthesises CMakeLists.txt contents + changed-file lists to verify
the parser + intersection logic. No git dependency.
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
    path = SCRIPTS_DIR / "cpp_mutation_targets.py"
    spec = importlib.util.spec_from_file_location("cpp_mutation_targets", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cpp_mutation_targets"] = module
    spec.loader.exec_module(module)
    return module


m = _load()


_FIXTURE = """\
cmake_minimum_required(VERSION 3.20)
project(xf_extensions LANGUAGES CXX)

add_executable(test_scoring tests/test_scoring.cpp scoring.cpp)
add_executable(test_passagesim tests/test_passagesim.cpp passagesim.cpp)
add_executable(test_simsearch tests/test_simsearch.cpp simsearch.cpp)

set(XF_GTEST_TARGETS
  test_scoring
  test_passagesim
  test_simsearch
)
"""


class ParseCMakeTests(unittest.TestCase):
    """`_parse_cmake` extracts binary -> source-set + XF_GTEST_TARGETS order."""

    def test_extracts_binary_to_sources(self):
        bin_map, order = m._parse_cmake(_FIXTURE)
        self.assertIn("test_scoring", bin_map)
        self.assertEqual(
            bin_map["test_scoring"],
            {"tests/test_scoring.cpp", "scoring.cpp"},
        )

    def test_extracts_target_order(self):
        _, order = m._parse_cmake(_FIXTURE)
        self.assertEqual(order, ["test_scoring", "test_passagesim", "test_simsearch"])

    def test_missing_targets_list_returns_empty(self):
        text = _FIXTURE.replace("XF_GTEST_TARGETS", "OTHER_LIST")
        _, order = m._parse_cmake(text)
        self.assertEqual(order, [])


class BinariesForChangedTests(unittest.TestCase):
    """`_binaries_for_changed` intersects changed-files with binary sources."""

    def setUp(self):
        self.bin_map, self.order = m._parse_cmake(_FIXTURE)

    def test_single_changed_cpp_returns_single_binary(self):
        # `backend/extensions/scoring.cpp` should map to test_scoring.
        changed = ["backend/extensions/scoring.cpp"]
        hits = m._binaries_for_changed(self.bin_map, self.order, changed)
        self.assertEqual(hits, ["test_scoring"])

    def test_two_changed_files_return_both_binaries(self):
        changed = ["backend/extensions/scoring.cpp",
                   "backend/extensions/simsearch.cpp"]
        hits = m._binaries_for_changed(self.bin_map, self.order, changed)
        self.assertEqual(sorted(hits), ["test_scoring", "test_simsearch"])

    def test_unrelated_change_returns_empty(self):
        changed = ["backend/extensions/unrelated.cpp"]
        hits = m._binaries_for_changed(self.bin_map, self.order, changed)
        self.assertEqual(hits, [])

    def test_test_file_change_also_returns_binary(self):
        # `tests/test_scoring.cpp` is a direct source of test_scoring.
        changed = ["backend/extensions/tests/test_scoring.cpp"]
        hits = m._binaries_for_changed(self.bin_map, self.order, changed)
        self.assertEqual(hits, ["test_scoring"])


class ShouldBroadcastTests(unittest.TestCase):
    """`_should_broadcast` forces all-binaries for header changes."""

    def test_header_change_broadcasts(self):
        self.assertTrue(m._should_broadcast(["backend/extensions/util.h"]))

    def test_include_dir_broadcasts(self):
        self.assertTrue(m._should_broadcast(["backend/extensions/include/foo.h"]))

    def test_cpp_only_does_not_broadcast(self):
        self.assertFalse(m._should_broadcast(["backend/extensions/scoring.cpp"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
