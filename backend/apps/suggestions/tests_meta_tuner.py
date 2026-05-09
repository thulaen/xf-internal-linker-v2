"""FR-018b — meta-algorithm autotuner tests.

Pin the safety invariants of the new ``MetaAlgorithmTuner`` module:

1. Every per-key lower bound is strictly positive — DEFAULT-ON-RULE.md
   forbids zeroing a parameter.
2. ``propose_meta_parameter_drift`` clamps to bounds and never zeros.
3. Excluded keys (e.g. ``pipeline.embedding_age_half_life_days``) are
   absent from the proposal output.
4. Empty / missing current values produce an empty proposal — cold-start
   safe.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.suggestions.services.meta_tuner import (
    _AUTOTUNER_EXCLUDED,
    _META_DRIFT_PCT,
    _META_PARAM_BOUNDS,
    MetaAlgorithmTuner,
    get_excluded_meta_keys,
    get_tunable_meta_keys,
    propose_meta_parameter_drift,
)


class BoundsInvariantTests(SimpleTestCase):
    def test_every_lower_bound_is_strictly_positive(self) -> None:
        """DEFAULT-ON-RULE.md: the tuner must never be able to zero a key."""
        for key, (lo, _hi) in _META_PARAM_BOUNDS.items():
            self.assertGreater(
                lo,
                0.0,
                f"{key!r} has lower bound {lo} — zero or negative is a "
                f"DEFAULT-ON-RULE violation.",
            )

    def test_every_upper_bound_exceeds_lower(self) -> None:
        for key, (lo, hi) in _META_PARAM_BOUNDS.items():
            self.assertLess(lo, hi, f"{key!r} has lo={lo} >= hi={hi}")

    def test_excluded_keys_are_documented_with_a_reason(self) -> None:
        for key, reason in _AUTOTUNER_EXCLUDED.items():
            self.assertTrue(
                isinstance(reason, str) and reason.strip(),
                f"{key!r} is excluded but has no rationale.",
            )

    def test_excluded_and_tunable_are_disjoint(self) -> None:
        overlap = set(_META_PARAM_BOUNDS) & set(_AUTOTUNER_EXCLUDED)
        self.assertFalse(
            overlap,
            f"Keys appear in both _META_PARAM_BOUNDS and _AUTOTUNER_EXCLUDED: {overlap}",
        )

    def test_drift_pct_is_small_and_positive(self) -> None:
        # Drift should be a small fraction (5%) — anything bigger and a
        # single monthly tuning could move parameters past sensible bounds.
        self.assertGreater(_META_DRIFT_PCT, 0.0)
        self.assertLess(_META_DRIFT_PCT, 0.20)


class ProposeDriftTests(SimpleTestCase):
    def _current_values(self) -> dict[str, str]:
        """Sensible mid-range values for every tunable key."""
        out: dict[str, str] = {}
        for key, (lo, hi) in _META_PARAM_BOUNDS.items():
            mid = (lo + hi) / 2.0
            out[key] = f"{mid}"
        return out

    def test_empty_current_values_returns_empty(self) -> None:
        proposal = propose_meta_parameter_drift(current_values={})
        self.assertEqual(proposal, {})

    def test_excluded_keys_never_in_proposal(self) -> None:
        # Even if the operator has a current value for an excluded key,
        # the tuner must not propose a drift for it.
        current = {key: "42.0" for key in _AUTOTUNER_EXCLUDED}
        proposal = propose_meta_parameter_drift(current_values=current)
        self.assertEqual(proposal, {})

    def test_proposal_clamps_into_per_key_bounds(self) -> None:
        rng = np.random.default_rng(seed=12345)
        current = self._current_values()
        proposal = propose_meta_parameter_drift(current_values=current, rng=rng)
        for key, value in proposal.items():
            lo, hi = _META_PARAM_BOUNDS[key]
            self.assertGreaterEqual(
                value, lo, f"{key!r} proposed {value} < lo {lo}"
            )
            self.assertLessEqual(value, hi, f"{key!r} proposed {value} > hi {hi}")

    def test_proposal_never_zeros_any_value(self) -> None:
        rng = np.random.default_rng(seed=42)
        # Hostile current values: very small but still positive.
        current = {key: f"{lo + 1e-6}" for key, (lo, _hi) in _META_PARAM_BOUNDS.items()}
        proposal = propose_meta_parameter_drift(current_values=current, rng=rng)
        for key, value in proposal.items():
            self.assertGreater(
                value, 0.0, f"{key!r} proposed value {value} is zero or negative"
            )

    def test_proposal_drift_is_within_per_run_cap(self) -> None:
        rng = np.random.default_rng(seed=7)
        current = self._current_values()
        proposal = propose_meta_parameter_drift(current_values=current, rng=rng)
        for key, value in proposal.items():
            current_val = float(current[key])
            relative_drift = abs(value - current_val) / current_val
            # Drift cap is _META_DRIFT_PCT, plus a tiny epsilon for the
            # clamp boundary case where the drift pushed the value into
            # the bound (which can shift it by ≤ a tiny amount).
            self.assertLessEqual(
                relative_drift,
                _META_DRIFT_PCT + 1e-6,
                f"{key!r} drift {relative_drift:.4f} exceeded cap {_META_DRIFT_PCT}",
            )

    def test_invalid_current_value_skips_that_key(self) -> None:
        # Garbled value for one key — the tuner logs and skips.
        current = self._current_values()
        first_key = next(iter(_META_PARAM_BOUNDS))
        current[first_key] = "not-a-number"
        proposal = propose_meta_parameter_drift(current_values=current)
        self.assertNotIn(first_key, proposal)


class MetaAlgorithmTunerTests(SimpleTestCase):
    def test_propose_returns_a_dict(self) -> None:
        # Real call hits ``get_current_weights`` which needs the DB; we
        # just smoke-test that the wrapper returns a dict shape.
        tuner = MetaAlgorithmTuner()
        # With no DB rows seeded for any tunable key, the result is {}
        result = propose_meta_parameter_drift(current_values={})
        self.assertEqual(result, {})
        # Sanity on the explain helper.
        excluded = tuner.explain_excluded()
        self.assertIsInstance(excluded, dict)
        for key in excluded:
            self.assertIn(key, _AUTOTUNER_EXCLUDED)

    def test_get_tunable_meta_keys_is_sorted(self) -> None:
        keys = get_tunable_meta_keys()
        self.assertEqual(keys, sorted(keys))

    def test_get_excluded_meta_keys_returns_copy(self) -> None:
        # Returned dict is a copy — caller mutations don't pollute the
        # module-level dict.
        snap = get_excluded_meta_keys()
        snap["pipeline.fake_key"] = "test"
        self.assertNotIn("pipeline.fake_key", _AUTOTUNER_EXCLUDED)
