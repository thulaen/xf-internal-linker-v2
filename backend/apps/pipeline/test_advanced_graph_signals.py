"""Tests for the advanced graph signals dispatcher (FR-260 to FR-265).

The signal MATH is covered by the Rust kernel's own tests
(rust/extensions/advanced_graph_signals). These tests cover the Python
dispatcher's behaviour: it must read the DESTINATION node's values (not the
host's) for TOSD/ICPC/RGSD, fall back to a neutral 0.0 when a node is missing,
weight each signal correctly, and emit spec-shaped diagnostics. A controlled
(mock) kernel makes the dispatcher's transformations deterministic; one
integration test exercises the real kernel when its compiled module is present.
"""

from __future__ import annotations

from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.advanced_graph_signals import (
    AdvancedGraphSignalsCaches,
    AdvancedGraphSignalsSettings,
    CSBRSettings,
    DSTPSettings,
    ICPCSettings,
    RGSDSettings,
    SBMASettings,
    TOSDSettings,
    evaluate_advanced_graph_signals_batch,
)

KERNEL_PATH = "apps.pipeline.services.advanced_graph_signals.load_kernel"

HOST = (1, "host")
DEST = (2, "dest")
# evaluate_batch positional-arg indices (mirrors the Rust signature order).
ARG_SPECTRAL, ARG_TRANSITION, ARG_OUTDEG = 0, 2, 3
ARG_LOCAL, ARG_GLOBAL = 5, 6
ARG_BLOCK, ARG_FLAT, ARG_DENSITY, ARG_PERSONA = 7, 8, 9, 12


def _caches() -> AdvancedGraphSignalsCaches:
    """Two nodes (host index 0, dest index 1) with deliberately distinct values
    so a host-vs-dest index mistake is caught."""
    return AdvancedGraphSignalsCaches(
        node_to_index={HOST: 0, DEST: 1},
        spectral_scores=np.array([9.0, 2.0]),  # host 9.0, dest 2.0
        transition_counts={(0, 1): 5},
        out_degrees=np.array([10, 3], dtype=np.int32),  # host out 10
        local_degrees=np.array([99, 5], dtype=np.int32),  # dest local 5
        global_degrees=np.array([99, 20], dtype=np.int32),  # dest global 20
        block_probabilities={(0, 1): 0.75},
        flat_distances={(0, 1): 0.2},
        density_gradients=np.array([99.0, 1.0]),  # dest density 1.0
        persona_matches={(0, 1): 0.85},
    )


def _all_disabled() -> AdvancedGraphSignalsSettings:
    return AdvancedGraphSignalsSettings(
        tosd=TOSDSettings(enabled=False),
        dstp=DSTPSettings(enabled=False),
        icpc=ICPCSettings(enabled=False),
        sbma=SBMASettings(enabled=False),
        rgsd=RGSDSettings(enabled=False),
        csbr=CSBRSettings(enabled=False),
    )


def _mock_kernel(**per_signal: float):
    """A kernel stand-in whose evaluate_batch returns fixed per-signal scores."""
    kernel = mock.MagicMock()

    def _evaluate_batch(spectral_scores, *args, **kwargs):
        n = len(spectral_scores)
        return {
            f"score_{s}": np.full(n, per_signal.get(s, 0.0))
            for s in ("tosd", "dstp", "icpc", "sbma", "rgsd", "csbr")
        }

    kernel.evaluate_batch.side_effect = _evaluate_batch
    return kernel


class DispatcherInputRoutingTests(SimpleTestCase):
    def test_destination_centric_signals_read_the_destination_node(self):
        kernel = _mock_kernel()
        with mock.patch(KERNEL_PATH, return_value=kernel):
            evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], _caches(), AdvancedGraphSignalsSettings(), [True]
            )
        args = kernel.evaluate_batch.call_args.args
        # TOSD/ICPC/RGSD must use the DESTINATION's per-node values...
        self.assertEqual(args[ARG_SPECTRAL][0], 2.0)
        self.assertEqual(args[ARG_LOCAL][0], 5)
        self.assertEqual(args[ARG_GLOBAL][0], 20)
        self.assertEqual(args[ARG_DENSITY][0], 1.0)
        # ...while DSTP's out-transition total stays the HOST's.
        self.assertEqual(args[ARG_OUTDEG][0], 10)
        # Pair lookups resolve on (host_index, dest_index).
        self.assertEqual(args[ARG_TRANSITION][0], 5)
        self.assertEqual(args[ARG_BLOCK][0], 0.75)
        self.assertEqual(args[ARG_FLAT][0], 0.2)
        self.assertEqual(args[ARG_PERSONA][0], 0.85)

    def test_sbma_uses_node_blocks_and_transition_matrix_when_available(self):
        caches = AdvancedGraphSignalsCaches(
            node_to_index={HOST: 0, DEST: 1},
            spectral_scores=np.zeros(2, dtype=np.float64),
            transition_counts={},
            out_degrees=np.zeros(2, dtype=np.int32),
            local_degrees=np.zeros(2, dtype=np.int32),
            global_degrees=np.zeros(2, dtype=np.int32),
            block_probabilities={},
            flat_distances={},
            density_gradients=np.zeros(2, dtype=np.float64),
            persona_matches={},
            node_blocks=np.array([0, 1], dtype=np.int32),
            block_transition_matrix={(0, 1): 0.75},
        )

        kernel = _mock_kernel()
        with mock.patch(KERNEL_PATH, return_value=kernel):
            evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], caches, AdvancedGraphSignalsSettings(), [False]
            )

        args = kernel.evaluate_batch.call_args.args
        self.assertEqual(args[ARG_BLOCK][0], 0.75)

    def test_missing_pair_defaults_to_farthest_distance(self):
        kernel = _mock_kernel()
        caches = _caches()
        caches.flat_distances.clear()  # resolved dest, but no recorded distance
        with mock.patch(KERNEL_PATH, return_value=kernel):
            evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], caches, AdvancedGraphSignalsSettings(), [True]
            )
        self.assertEqual(kernel.evaluate_batch.call_args.args[ARG_FLAT][0], 1.0)


class DispatcherFallbackTests(SimpleTestCase):
    def test_missing_node_forces_neutral_zero(self):
        # Even though the kernel returns 0.5 for everything, an unresolved
        # candidate must score the neutral 0.0 with fallback_triggered=True.
        kernel = _mock_kernel(tosd=0.5, dstp=0.5, icpc=0.5, sbma=0.5, rgsd=0.5, csbr=0.5)
        with mock.patch(KERNEL_PATH, return_value=kernel):
            [ev] = evaluate_advanced_graph_signals_batch(
                [(HOST, (9, "unknown"))], _caches(), AdvancedGraphSignalsSettings(), [True]
            )
        self.assertEqual(ev.weighted_contribution, 0.0)
        self.assertTrue(all(v == 0.0 for v in ev.per_signal_scores.values()))
        self.assertTrue(ev.per_signal_diagnostics["tosd_diagnostics"]["fallback_triggered"])

    def test_no_caches_is_cold_start(self):
        [ev] = evaluate_advanced_graph_signals_batch(
            [(HOST, DEST)], None, AdvancedGraphSignalsSettings(), [True]
        )
        self.assertEqual(ev.per_signal_scores["score_tosd"], 0.0)
        self.assertEqual(
            ev.per_signal_diagnostics["tosd_diagnostics"]["reason"], "cold_start_no_graph"
        )

    def test_all_disabled_is_inactive(self):
        [ev] = evaluate_advanced_graph_signals_batch(
            [(HOST, DEST)], _caches(), _all_disabled(), [True]
        )
        self.assertEqual(ev.weighted_contribution, 0.0)


class DispatcherWeightingTests(SimpleTestCase):
    def test_contribution_is_weighted_sum(self):
        kernel = _mock_kernel(tosd=0.5, icpc=1.0)  # others 0.0
        with mock.patch(KERNEL_PATH, return_value=kernel):
            [ev] = evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], _caches(), AdvancedGraphSignalsSettings(), [True]
            )
        # 0.5 * 0.06 (tosd) + 1.0 * 0.04 (icpc)
        self.assertAlmostEqual(ev.weighted_contribution, 0.5 * 0.06 + 1.0 * 0.04)

    def test_disabled_signal_scores_zero_but_others_compute(self):
        settings = AdvancedGraphSignalsSettings(tosd=TOSDSettings(enabled=False))
        kernel = _mock_kernel(tosd=0.9, icpc=0.5)
        with mock.patch(KERNEL_PATH, return_value=kernel):
            [ev] = evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], _caches(), settings, [True]
            )
        self.assertEqual(ev.per_signal_scores["score_tosd"], 0.0)
        self.assertFalse(ev.per_signal_diagnostics["tosd_diagnostics"]["enabled"])
        self.assertEqual(ev.per_signal_scores["score_icpc"], 0.5)


class DispatcherDiagnosticsTests(SimpleTestCase):
    def test_diagnostics_carry_real_inputs(self):
        kernel = _mock_kernel(sbma=0.75)
        with mock.patch(KERNEL_PATH, return_value=kernel):
            [ev] = evaluate_advanced_graph_signals_batch(
                [(HOST, DEST)], _caches(), AdvancedGraphSignalsSettings(), [True]
            )
        d = ev.per_signal_diagnostics
        self.assertEqual(d["icpc_diagnostics"]["local_indegree"], 5)
        self.assertEqual(d["icpc_diagnostics"]["global_indegree"], 20)
        self.assertEqual(d["dstp_diagnostics"]["out_degree"], 10)
        self.assertEqual(d["dstp_diagnostics"]["transition_count"], 5)
        self.assertEqual(d["sbma_diagnostics"]["block_probability"], 0.75)
        self.assertEqual(d["csbr_diagnostics"]["persona_match"], 0.85)
        self.assertTrue(d["csbr_diagnostics"]["is_cross_silo"])
        self.assertFalse(d["tosd_diagnostics"]["fallback_triggered"])


class RealKernelIntegrationTests(SimpleTestCase):
    """End-to-end through the real compiled kernel (skipped if not built)."""

    def test_real_kernel_known_answers(self):
        from apps.pipeline.services.rust_kernels import load_kernel

        try:
            load_kernel("extensions.advanced_graph_signals", "evaluate_batch")
        except Exception as exc:  # noqa: BLE001 - skip when the .so is absent
            self.skipTest(f"advanced_graph_signals kernel unavailable: {exc}")

        [ev] = evaluate_advanced_graph_signals_batch(
            [(HOST, DEST)], _caches(), AdvancedGraphSignalsSettings(), [True]
        )
        s = ev.per_signal_scores
        # Hand-computed against the dest-indexed cache values.
        self.assertAlmostEqual(s["score_tosd"], 1.0 / (1.0 + 0.8 * 2.0))  # lambda 2.0
        self.assertAlmostEqual(s["score_sbma"], 0.75)
        self.assertAlmostEqual(s["score_icpc"], float(np.log(6) / np.log(21)))
        self.assertAlmostEqual(s["score_dstp"], 5.0 / (10.0 + 5.0))
        self.assertAlmostEqual(s["score_csbr"], (0.85 - 0.7) / (1.0 - 0.7))
