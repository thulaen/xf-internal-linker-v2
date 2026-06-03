"""Convention tests pinning the scoring C++ kernel public binding name.

``backend/extensions/scoring.cpp`` exports its pybind11 function under the name
``calculate_composite_scores_full_batch``. The native-runtime health check in
``apps.diagnostics.health._NATIVE_RUNTIME_MODULES`` asserts that exact attribute
is present on the loaded ``scoring`` module, and the Python ranker / benchmark
callers invoke it by that name. If the ``m.def("...")`` literal in the .cpp ever
drifts back to the old ``score_full_batch`` name, the health check and every
caller break at runtime, but nothing fails at compile time.

These tests read the source files directly (no compilation, no native import)
so they run in the lean test image and pin the literal so a mutmut / rename
regression on the changed ``m.def`` line is caught.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCORING_CPP = _REPO_ROOT / "backend" / "extensions" / "scoring.cpp"
_HEALTH_PY = _REPO_ROOT / "backend" / "apps" / "diagnostics" / "health.py"

_EXPECTED_BINDING = "calculate_composite_scores_full_batch"


class ScoringBindingConventionTests(SimpleTestCase):
    def test_scoring_cpp_exports_expected_binding_name(self) -> None:
        source = _SCORING_CPP.read_text(encoding="utf-8")
        self.assertIn(
            f'm.def("{_EXPECTED_BINDING}"',
            source,
            "scoring.cpp must export the binding under the name the health "
            "check and Python callers expect.",
        )

    def test_scoring_cpp_no_longer_exports_old_binding_name(self) -> None:
        source = _SCORING_CPP.read_text(encoding="utf-8")
        self.assertNotIn(
            'm.def("score_full_batch"',
            source,
            "The old binding name must not be re-exported; health.py expects "
            "the renamed binding.",
        )

    def test_health_module_list_references_expected_binding(self) -> None:
        source = _HEALTH_PY.read_text(encoding="utf-8")
        self.assertIn(
            _EXPECTED_BINDING,
            source,
            "health.py _NATIVE_RUNTIME_MODULES must check the same binding name "
            "scoring.cpp exports.",
        )
