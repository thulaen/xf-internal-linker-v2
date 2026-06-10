"""Phase 7 — the Optuna search space is REGISTRY-DRIVEN.

Core acceptance test for Slice 15 / Phase 7:

    A new tunable registered in ``suggestions/tunable_registry.py`` MUST
    automatically appear in the Optuna search space WITHOUT editing any
    tuner code (no new ``SearchSpaceEntry``, no edit to
    ``meta_hpo_search_spaces`` / ``meta_hpo`` / ``meta_tuner`` /
    ``weight_tuner``).

The deriver (:func:`derive_registry_search_space`) reads the registry's
``META_PARAMS`` / ``BLEND_WEIGHTS`` / ``CONDITIONAL_BLEND_WEIGHTS`` and
emits one Optuna ``SearchSpaceEntry`` per entry — distribution, clip
bounds, and serialiser all inferred from the registry fields. Adding a
registry entry therefore extends the search space with zero tuner-code
change.

§F boundary note: this is ``ranking_train`` — Python may TRAIN/COMPARE
candidate profiles offline only. Nothing here activates, promotes, or
rolls back a profile; activation stays gated by Rust governance + GUI
approval. These tests touch the offline search-space derivation only.
"""

from __future__ import annotations

from unittest.mock import patch

import optuna
from django.test import SimpleTestCase

from apps.pipeline.services import meta_hpo_search_spaces as mhss
from apps.suggestions.tunable_registry import TunableEntry


class _StubTrial:
    """Records every suggest_* call so a test can assert the distribution.

    Returns the midpoint of the requested range for floats/ints and the
    first choice for categoricals — deterministic, no Optuna sampler.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def suggest_float(self, name, lo, hi, *, log=False):
        self.calls.append(("float", name, lo, hi, log))
        return (lo + hi) / 2.0

    def suggest_int(self, name, lo, hi):
        self.calls.append(("int", name, lo, hi))
        return int((lo + hi) // 2)

    def suggest_categorical(self, name, choices):
        self.calls.append(("categorical", name, tuple(choices)))
        return choices[0]


class RegistryDrivenSearchSpaceTests(SimpleTestCase):
    """The deriver turns registry entries into Optuna search-space entries."""

    def test_new_registry_meta_param_auto_appears_without_tuner_edit(self) -> None:
        """The Phase 7 acceptance: register a brand-new tunable in
        ``META_PARAMS`` and confirm it appears in the derived search space
        — without editing ``meta_hpo_search_spaces`` or any tuner code.
        """
        from apps.suggestions import tunable_registry

        new_key = "pipeline.brand_new_phase7_knob"
        patched = dict(tunable_registry.META_PARAMS)
        patched[new_key] = TunableEntry(
            lower=0.10,
            upper=0.90,
            default="0.50",
            citation="test-only — proves registry-driven derivation",
        )
        with patch.object(tunable_registry, "META_PARAMS", patched):
            derived = mhss.derive_registry_search_space()

        derived_keys = {entry.app_setting_key for entry in derived}
        self.assertIn(
            new_key,
            derived_keys,
            "A newly-registered META_PARAMS key did not appear in the "
            "derived Optuna search space — Phase 7 acceptance failed.",
        )

    def test_new_registry_meta_param_flows_into_live_search_space(self) -> None:
        """End-to-end: the live ``SEARCH_SPACE`` (what ``meta_hpo`` iterates)
        includes the new registry key after rebuild, with no tuner edit.
        """
        from apps.suggestions import tunable_registry

        new_key = "slate_diversity.brand_new_cap"
        patched = dict(tunable_registry.META_PARAMS)
        patched[new_key] = TunableEntry(
            lower=0.5,
            upper=1.0,
            default="0.80",
            citation="test-only",
        )
        with patch.object(tunable_registry, "META_PARAMS", patched):
            space = mhss.build_search_space()

        self.assertIn(new_key, {e.app_setting_key for e in space})

    def test_blend_weight_keys_are_derived(self) -> None:
        derived_keys = {e.app_setting_key for e in mhss.derive_registry_search_space()}
        for w_key in ("w_semantic", "w_keyword", "w_node", "w_quality"):
            self.assertIn(w_key, derived_keys)

    def test_integer_default_yields_int_distribution(self) -> None:
        """``pipeline.rrf_k`` (default ``"60"``) must use ``suggest_int``."""
        entry = self._entry_for("pipeline.rrf_k")
        trial = _StubTrial()
        entry.suggest(trial)
        kind = trial.calls[0][0]
        self.assertEqual(kind, "int", "rrf_k has an integer default; expected suggest_int")

    def test_float_default_yields_float_distribution(self) -> None:
        """``pipeline.bm25_k1`` (default ``"1.2"``) must use ``suggest_float``."""
        entry = self._entry_for("pipeline.bm25_k1")
        trial = _StubTrial()
        entry.suggest(trial)
        self.assertEqual(trial.calls[0][0], "float")

    def test_clip_clamps_into_registry_bounds(self) -> None:
        entry = self._entry_for("pipeline.bm25_k1")  # bounds 0.5..3.0
        self.assertEqual(entry.clip(99.0), 3.0)
        self.assertEqual(entry.clip(-1.0), 0.5)

    def test_serialiser_round_trips_default(self) -> None:
        """``to_appsetting`` must produce a string that re-parses to a number."""
        entry = self._entry_for("pipeline.bm25_k1")
        serialised = entry.to_appsetting(1.25)
        self.assertIsInstance(serialised, str)
        self.assertAlmostEqual(float(serialised), 1.25, places=3)

    def test_int_serialiser_emits_no_decimal_point(self) -> None:
        entry = self._entry_for("pipeline.rrf_k")
        serialised = entry.to_appsetting(60.0)
        self.assertNotIn(".", serialised)
        self.assertEqual(int(serialised), 60)

    def test_derived_keys_are_unique(self) -> None:
        derived = mhss.derive_registry_search_space()
        seen: set[str] = set()
        for entry in derived:
            self.assertNotIn(entry.app_setting_key, seen)
            seen.add(entry.app_setting_key)

    def test_derived_suggest_is_optuna_compatible(self) -> None:
        """The derived suggest callable works with a real Optuna trial."""
        entry = self._entry_for("pipeline.bm25_k1")
        study = optuna.create_study(direction="maximize")

        def objective(trial):
            value = entry.suggest(trial)
            self.assertGreaterEqual(value, 0.5)
            self.assertLessEqual(value, 3.0)
            return float(value)

        study.optimize(objective, n_trials=3)

    def _entry_for(self, key: str):
        for entry in mhss.derive_registry_search_space():
            if entry.app_setting_key == key:
                return entry
        self.fail(f"derived search space is missing expected key {key!r}")
        return None
