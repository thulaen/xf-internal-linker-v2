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

_APP_DIR = Path(__file__).resolve().parents[2]
_SCORING_CPP = _APP_DIR / "extensions" / "scoring.cpp"
_HEALTH_PY = _APP_DIR / "apps" / "diagnostics" / "health.py"

# The Python runtime call sites that probe the ``scoring`` module by attribute
# name. If any of these drifts back to the old ``score_full_batch`` name, the
# attribute probe fails at runtime and the kernel silently falls back to the
# pure-Python loop (10-50x slower) with no compile-time error.
_BACKEND = _APP_DIR / "apps"
_RUNTIME_CALL_SITES = (
    _BACKEND / "pipeline" / "services" / "ranker.py",
    _BACKEND / "pipeline" / "services" / "ext_loader.py",
    _BACKEND / "crawler" / "tasks.py",
)

_EXPECTED_BINDING = "calculate_composite_scores_full_batch"
_OLD_BINDING = "score_full_batch"


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

    def test_runtime_call_sites_probe_new_binding_name(self) -> None:
        """Each runtime caller must reference the renamed binding.

        Guards against the silent-fallback regression: probing the loaded
        ``scoring`` module for the old ``score_full_batch`` attribute always
        returns ``None`` after the rename, forcing the slow Python path.
        """
        for path in _RUNTIME_CALL_SITES:
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                _EXPECTED_BINDING,
                source,
                f"{path.name} must probe the renamed scoring binding.",
            )

    def test_runtime_call_sites_have_no_active_old_binding_reference(self) -> None:
        """No executable line may reference the old binding name.

        Comments may still mention ``score_full_batch`` for historical
        context, and the Python reference helper ends in ``_py``; both are
        excluded so only an active code reference to the bare old name fails.
        """
        for path in _RUNTIME_CALL_SITES:
            offenders = []
            for lineno, raw in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                code = raw.split("#", 1)[0]
                stripped = code.replace(_EXPECTED_BINDING, "")
                # Drop the Python reference helper ``..._full_batch_py`` so its
                # ``score_full_batch`` substring does not trip the check.
                stripped = stripped.replace(f"{_OLD_BINDING}_py", "")
                if _OLD_BINDING in stripped:
                    offenders.append(f"{path.name}:{lineno}: {raw.strip()}")
            self.assertEqual(
                offenders,
                [],
                "Active old-binding references would silently disable the "
                f"C++ scoring kernel: {offenders}",
            )
