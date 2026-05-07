"""Tests for the FR-242/243/245/246 scaffolds shipped 2026-05-07.

Each scaffold module ships with vanilla-fallback / cold-start defaults
so the tests run without external dependencies (no NLTK, no LoRA
weights file, no DB). Sources of truth are inline in each module.
"""

from __future__ import annotations

import os
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.domain_adapter import (
    GPL_MIN_CORPUS_SIZE,
    LORA_ALPHA_DEFAULT,
    LORA_RANK_DEFAULT,
    get_adapter_status,
    get_adapter_weights_path,
    has_trained_adapter,
    load_adapted_model,
    should_train_adapter,
)
from apps.pipeline.services.nrt_delta_index import (
    DELTA_FLUSH_THRESHOLD_DEFAULT,
    DELTA_MAX_SIZE_DEFAULT,
    NRTDeltaIndex,
    get_live_delta,
    reset_live_delta,
)
from apps.pipeline.services.polysemy_gate import (
    MIN_POLYSEMY_THRESHOLD,
    PolysemyDiagnostic,
    detect_polysemous_terms,
    gate_polysemy,
    get_polysemy_status,
)
from apps.pipeline.services.score_calibration import (
    COLD_START_PARAMS,
    MIN_CALIBRATED_PROBABILITY_DEFAULT,
    PlattParams,
    VALIDATION_SET_MIN_SIZE_DEFAULT,
    calibrated_probability,
    fit_platt_sigmoid,
    passes_calibrated_threshold,
)


# ─────────────────────────────────────────────────────────────────────
# FR-242 — Domain adapter
# ─────────────────────────────────────────────────────────────────────


class DomainAdapterTests(SimpleTestCase):
    """Wang et al. 2022 GPL §4 minimum-data threshold + cold-start fallback."""

    def test_constants_locked_to_paper_defaults(self):
        # Wang 2022 GPL §4 minimum corpus, Hu 2021 LoRA §4.1 rank/alpha.
        self.assertEqual(GPL_MIN_CORPUS_SIZE, 10_000)
        self.assertEqual(LORA_RANK_DEFAULT, 8)
        self.assertEqual(LORA_ALPHA_DEFAULT, 16)

    def test_should_train_adapter_below_minimum_returns_false(self):
        # Wang 2022 §4 — below 10K docs, GPL collapses to noise.
        self.assertFalse(should_train_adapter(0))
        self.assertFalse(should_train_adapter(9_999))

    def test_should_train_adapter_at_minimum_returns_true(self):
        self.assertTrue(should_train_adapter(10_000))
        self.assertTrue(should_train_adapter(1_000_000))

    def test_no_trained_adapter_returns_vanilla_unchanged(self):
        # Cold-start happy path: no LoRA weights on disk → vanilla
        # passes through unchanged.
        sentinel = object()
        with mock.patch(
            "apps.pipeline.services.domain_adapter.has_trained_adapter",
            return_value=False,
        ):
            out = load_adapted_model(sentinel)
        self.assertIs(out, sentinel)

    def test_adapter_load_failure_falls_back_to_vanilla(self):
        # Adversarial: adapter file present but loader stub raises
        # NotImplementedError. Documented behaviour: catch + log +
        # fall back to vanilla. Pipeline must not crash.
        sentinel = object()
        with mock.patch(
            "apps.pipeline.services.domain_adapter.has_trained_adapter",
            return_value=True,
        ):
            out = load_adapted_model(sentinel)
        self.assertIs(out, sentinel)

    def test_status_helper_returns_expected_shape(self):
        status = get_adapter_status()
        self.assertIn("available", status)
        self.assertIn("path", status)
        self.assertIn("weights_path", status)

    def test_weights_path_respects_env_override(self):
        with mock.patch.dict(
            os.environ, {"EMBEDDING_DOMAIN_ADAPTER_PATH": "/custom/path"}, clear=False,
        ):
            self.assertEqual(get_adapter_weights_path(), "/custom/path")


# ─────────────────────────────────────────────────────────────────────
# FR-243 — Polysemy gate
# ─────────────────────────────────────────────────────────────────────


class _FakeWordNet:
    """Tiny in-memory WordNet stand-in for tests."""

    def __init__(self, sense_counts: dict[str, int]):
        self._counts = sense_counts

    def synsets(self, term):
        # Return a list of dummy "synsets"; only len() matters to callers.
        return [object()] * self._counts.get(term.lower(), 0)


class PolysemyGateTests(SimpleTestCase):
    """Bevilacqua 2021 §2.1 — surface forms with ≥2 WordNet senses."""

    def test_threshold_constant_locked(self):
        self.assertEqual(MIN_POLYSEMY_THRESHOLD, 2)

    def test_no_wordnet_returns_empty_list(self):
        # Cold-start safe: NLTK absent → empty result, no crash.
        with mock.patch(
            "apps.pipeline.services.polysemy_gate._try_import_wordnet",
            return_value=None,
        ):
            self.assertEqual(detect_polysemous_terms("Apple bank river"), [])

    def test_polysemous_terms_detected(self):
        # "apple" (fruit + company) and "bank" (financial + riverbank)
        # are canonically polysemous. "table" has many senses too.
        wn = _FakeWordNet({"apple": 5, "bank": 8, "the": 1, "of": 1})
        terms = detect_polysemous_terms("apple bank the of", wordnet_module=wn)
        self.assertIn("apple", terms)
        self.assertIn("bank", terms)
        self.assertNotIn("the", terms)
        self.assertNotIn("of", terms)

    def test_single_sense_excluded(self):
        # Below the polysemy threshold → not flagged.
        wn = _FakeWordNet({"docker": 1})
        self.assertEqual(detect_polysemous_terms("docker", wordnet_module=wn), [])

    def test_empty_text_returns_empty(self):
        self.assertEqual(detect_polysemous_terms(""), [])

    def test_gate_polysemy_no_wordnet_path(self):
        with mock.patch(
            "apps.pipeline.services.polysemy_gate._try_import_wordnet",
            return_value=None,
        ):
            diag = gate_polysemy("Apple bank")
        self.assertIsInstance(diag, PolysemyDiagnostic)
        self.assertEqual(diag.polysemous_terms, ())
        self.assertEqual(diag.runtime_path, "no_wordnet")

    def test_gate_polysemy_with_wordnet_emits_terms(self):
        wn = _FakeWordNet({"apple": 5, "fruit": 1})
        diag = gate_polysemy("Apple fruit", wordnet_module=wn)
        self.assertIn("apple", diag.polysemous_terms)
        self.assertEqual(diag.runtime_path, "wordnet_lookup")

    def test_status_helper_returns_expected_shape(self):
        status = get_polysemy_status()
        self.assertIn("available", status)
        self.assertIn("path", status)
        self.assertIn("reason", status)


# ─────────────────────────────────────────────────────────────────────
# FR-245 — Platt calibration
# ─────────────────────────────────────────────────────────────────────


class PlattCalibrationTests(SimpleTestCase):
    """Platt 1999 §2 sigmoid + Niculescu-Mizil 2005 §4 minimum data."""

    def test_constants_locked(self):
        self.assertEqual(VALIDATION_SET_MIN_SIZE_DEFAULT, 1000)
        self.assertEqual(MIN_CALIBRATED_PROBABILITY_DEFAULT, 0.5)

    def test_calibrated_probability_in_unit_interval(self):
        # Platt 1999 §2 — sigmoid output is in (0, 1) by construction.
        for cosine in (-1.0, 0.0, 0.25, 0.5, 0.9, 1.0):
            p = calibrated_probability(cosine)
            self.assertGreater(p, 0.0)
            self.assertLess(p, 1.0)

    def test_higher_cosine_yields_higher_probability_under_cold_start(self):
        # Monotonicity: P(0.9) > P(0.5) > P(0.1) > P(-0.5).
        ps = [calibrated_probability(c) for c in (-0.5, 0.1, 0.5, 0.9)]
        for i in range(len(ps) - 1):
            self.assertLess(ps[i], ps[i + 1])

    def test_cold_start_decision_boundary_near_historical_cutoff(self):
        # Cold-start params target P(cosine=0.25) ≈ 0.5 — the
        # historical hardcoded cutoff. Within a few decimals.
        p = calibrated_probability(0.25)
        self.assertAlmostEqual(p, 0.5, places=1)

    def test_passes_threshold_with_default(self):
        # cosine=0.5 → P > 0.5 → passes default threshold.
        self.assertTrue(passes_calibrated_threshold(0.5))
        # cosine=0.0 → P < 0.5 → fails.
        self.assertFalse(passes_calibrated_threshold(0.0))

    def test_fit_below_minimum_returns_none(self):
        # Niculescu-Mizil 2005 §4 — < 1000 pairs is too few to fit.
        params = fit_platt_sigmoid([0.1, 0.9], [0, 1])
        self.assertIsNone(params)

    def test_fit_with_degenerate_labels_returns_none(self):
        # All-positive labels → degenerate; refuse fit.
        scores = [0.5] * 1000
        labels = [1] * 1000
        params = fit_platt_sigmoid(scores, labels)
        self.assertIsNone(params)

    def test_fit_on_synthetic_data_returns_params(self):
        # Synthetic logistic dataset: high cosine → label 1.
        rng = np.random.default_rng(seed=42)
        scores_list = rng.uniform(0.0, 1.0, size=2000).tolist()
        labels_list = [1 if s > 0.5 else 0 for s in scores_list]
        # Add some noise so the labels aren't perfectly separable.
        for i in range(0, 200):
            labels_list[i] = 1 - labels_list[i]
        params = fit_platt_sigmoid(scores_list, labels_list)
        self.assertIsNotNone(params)
        self.assertIsInstance(params, PlattParams)

    def test_score_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            fit_platt_sigmoid([0.1, 0.5], [1])


# ─────────────────────────────────────────────────────────────────────
# FR-246 — NRT delta FAISS scaffold
# ─────────────────────────────────────────────────────────────────────


def _unit(*vals: float) -> np.ndarray:
    v = np.asarray(vals, dtype=np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32)


class NRTDeltaIndexTests(SimpleTestCase):
    """Bialecki 2012 §3 NRT pattern + Yang 2018 §4 size cap."""

    def test_default_constants_locked(self):
        self.assertEqual(DELTA_MAX_SIZE_DEFAULT, 10_000)
        self.assertEqual(DELTA_FLUSH_THRESHOLD_DEFAULT, 5_000)

    def test_empty_index_search_returns_empty(self):
        idx = NRTDeltaIndex()
        self.assertEqual(idx.search(_unit(1.0, 0.0), k=5), [])
        self.assertEqual(idx.size(), 0)

    def test_add_then_search_finds_added_vector(self):
        idx = NRTDeltaIndex()
        v = _unit(1.0, 0.0)
        idx.add(42, "post", v)
        results = idx.search(v, k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 42)
        self.assertEqual(results[0][1], "post")
        self.assertAlmostEqual(results[0][2], 1.0, places=5)

    def test_top_k_ordering(self):
        # Higher cosine should rank first.
        idx = NRTDeltaIndex()
        idx.add(1, "post", _unit(0.0, 1.0))   # orthogonal to query
        idx.add(2, "post", _unit(1.0, 0.0))   # query itself
        idx.add(3, "post", _unit(0.7, 0.7))   # ~45° to query
        results = idx.search(_unit(1.0, 0.0), k=3)
        self.assertEqual([r[0] for r in results], [2, 3, 1])

    def test_fifo_eviction_on_overflow(self):
        # Yang 2018 §4 — FIFO eviction when full.
        idx = NRTDeltaIndex(max_size=3, flush_threshold=2)
        for pk in range(5):
            idx.add(pk, "post", _unit(1.0, float(pk) * 0.1))
        self.assertEqual(idx.size(), 3)
        # The oldest two (pk=0, pk=1) should have been evicted.
        results = idx.search(_unit(1.0, 0.0), k=10)
        pks = {r[0] for r in results}
        self.assertEqual(pks, {2, 3, 4})

    def test_refresh_existing_key_does_not_count_as_new(self):
        idx = NRTDeltaIndex(max_size=2, flush_threshold=1)
        idx.add(1, "post", _unit(1.0, 0.0))
        idx.add(2, "post", _unit(0.0, 1.0))
        # Refresh key 1 — should NOT evict key 2.
        idx.add(1, "post", _unit(1.0, 0.5))
        self.assertEqual(idx.size(), 2)

    def test_needs_flush_at_threshold(self):
        idx = NRTDeltaIndex(max_size=10, flush_threshold=3)
        for pk in range(2):
            idx.add(pk, "post", _unit(1.0, float(pk)))
        self.assertFalse(idx.needs_flush())
        idx.add(2, "post", _unit(1.0, 2.0))
        self.assertTrue(idx.needs_flush())

    def test_clear_empties_index(self):
        idx = NRTDeltaIndex()
        idx.add(1, "post", _unit(1.0, 0.0))
        idx.clear()
        self.assertEqual(idx.size(), 0)

    def test_host_pk_set_filter(self):
        idx = NRTDeltaIndex()
        idx.add(1, "post", _unit(1.0, 0.0))
        idx.add(2, "post", _unit(0.5, 0.5))
        results = idx.search(_unit(1.0, 0.0), k=5, host_pk_set={2})
        self.assertEqual([r[0] for r in results], [2])

    def test_invalid_max_size_raises(self):
        with self.assertRaises(ValueError):
            NRTDeltaIndex(max_size=0)

    def test_invalid_flush_threshold_raises(self):
        with self.assertRaises(ValueError):
            NRTDeltaIndex(max_size=10, flush_threshold=11)

    def test_non_1d_vector_rejected(self):
        idx = NRTDeltaIndex()
        with self.assertRaises(ValueError):
            idx.add(1, "post", np.zeros((2, 2), dtype=np.float32))

    def test_get_status_shape(self):
        idx = NRTDeltaIndex()
        idx.add(1, "post", _unit(1.0, 0.0))
        status = idx.get_status()
        self.assertEqual(status["size"], 1)
        self.assertEqual(status["max_size"], DELTA_MAX_SIZE_DEFAULT)
        self.assertFalse(status["needs_flush"])

    def test_singleton_helpers(self):
        reset_live_delta()
        a = get_live_delta()
        b = get_live_delta()
        self.assertIs(a, b)
        reset_live_delta()
        c = get_live_delta()
        self.assertIsNot(a, c)
