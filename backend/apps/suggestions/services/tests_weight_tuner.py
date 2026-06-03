"""Convention-named SimpleTestCase coverage for suggestions/services/weight_tuner.py.

The mutation gate discovers ``tests_<stem>.py`` in the SAME directory as the
stem. The pre-existing ``apps/suggestions/tests_weight_tuner.py`` lives one
directory up and uses the database-backed ``TestCase``; the gate looking next to
``weight_tuner.py`` never finds it. This file adds discoverable, hang-safe
coverage for the pure, database-free parts of the module:

* the module-level safety constants the autotuner is bound by, and
* the two pure NumPy helpers ``_normalize_weight_vector`` and
  ``_project_to_bounded_simplex``.

The 2026 refactor that switched the sample matrix from ``list.append`` loops to
``np.asarray(..., dtype=np.float64)`` feeds these helpers; pinning their exact
numeric output kills the changed-line literal/operator mutants without running
the L-BFGS-B optimiser, hitting the database, or making any network call.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.suggestions.services.weight_tuner import (
    _DRIFT_LIMIT_PER_RUN,
    _WEIGHT_EPSILON,
    _WEIGHT_FLOOR,
    _normalize_weight_vector,
    _project_to_bounded_simplex,
)


class SafetyConstantTests(SimpleTestCase):
    """Pin the exact safety literals so a +/-1 mutant on each one dies."""

    def test_drift_limit_is_exactly_five_hundredths(self) -> None:
        self.assertEqual(_DRIFT_LIMIT_PER_RUN, 0.05)

    def test_weight_floor_is_exactly_one_hundredth(self) -> None:
        # The DEFAULT-ON floor that the tuner is forbidden to drive below.
        self.assertEqual(_WEIGHT_FLOOR, 0.01)

    def test_weight_epsilon_is_exactly_1e_minus_9(self) -> None:
        self.assertEqual(_WEIGHT_EPSILON, 1e-9)


class NormalizeWeightVectorTests(SimpleTestCase):
    def test_sums_to_one(self) -> None:
        out = _normalize_weight_vector(np.array([1.0, 3.0]))
        self.assertAlmostEqual(float(np.sum(out)), 1.0, places=12)
        self.assertAlmostEqual(float(out[0]), 0.25, places=12)
        self.assertAlmostEqual(float(out[1]), 0.75, places=12)

    def test_empty_vector_returned_unchanged(self) -> None:
        out = _normalize_weight_vector(np.array([]))
        self.assertEqual(out.size, 0)

    def test_zero_total_falls_back_to_uniform(self) -> None:
        out = _normalize_weight_vector(np.array([0.0, 0.0, 0.0, 0.0]))
        # 1/len → exactly 0.25 for four entries; assertEqual kills a len(+1) mutant.
        for value in out:
            self.assertAlmostEqual(float(value), 0.25, places=12)


class ProjectToBoundedSimplexTests(SimpleTestCase):
    def test_clamps_within_bounds_and_keeps_sum_one(self) -> None:
        weights = np.array([0.7, 0.2, 0.1])
        lower = np.array([0.0, 0.0, 0.0])
        upper = np.array([0.4, 1.0, 1.0])
        out = _project_to_bounded_simplex(weights, lower, upper)
        self.assertLessEqual(float(out[0]), 0.4 + 1e-9)
        self.assertAlmostEqual(float(np.sum(out)), 1.0, places=9)

    def test_already_feasible_vector_keeps_sum_one(self) -> None:
        weights = np.array([0.25, 0.25, 0.25, 0.25])
        lower = np.zeros(4)
        upper = np.ones(4)
        out = _project_to_bounded_simplex(weights, lower, upper)
        self.assertAlmostEqual(float(np.sum(out)), 1.0, places=12)
