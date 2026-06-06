"""Focused coverage tests for ``apps.pipeline.services.hits.compute``.

These pin the non-empty directed-graph path of :func:`compute`, which is the
only path that reaches the in-function ``from extensions import pagerank``
import (line 112) and the C++ power-iteration loop after it. The empty-graph
and undirected guards short-circuit *before* that import, so without a
non-trivial directed graph the import line stays uncovered.

Kept in its own ``tests_hits.py`` module (matching the ``hits.py`` stem) so a
per-file coverage run that resolves ``hits.py`` -> ``tests_hits.py`` still
executes the kernel import path.
"""

from __future__ import annotations

import networkx as nx
from django.test import SimpleTestCase

from apps.pipeline.services.hits import HitsScores, compute, top_authorities, top_hubs


def _triangle() -> nx.DiGraph:
    """A small directed graph: 1 -> 2 -> 3 -> 1 plus a 1 -> 3 shortcut."""
    g = nx.DiGraph()
    g.add_edges_from([(1, 2), (2, 3), (3, 1), (1, 3)])
    return g


class HitsComputeKernelPathTests(SimpleTestCase):
    def test_non_empty_directed_graph_runs_kernel_import_path(self) -> None:
        # Reaches line 112 (`from extensions import pagerank`) and the power
        # iteration loop. The normalised scores must sum to ~1.0 and cover
        # every node, matching the networkx `normalized=True` convention.
        scores = compute(_triangle())

        self.assertIsInstance(scores, HitsScores)
        self.assertEqual(set(scores.authority), {1, 2, 3})
        self.assertEqual(set(scores.hub), {1, 2, 3})
        self.assertAlmostEqual(sum(scores.authority.values()), 1.0, places=6)
        self.assertAlmostEqual(sum(scores.hub.values()), 1.0, places=6)

    def test_node_3_is_top_authority_in_triangle(self) -> None:
        # Node 3 is pointed to by both 2 and 1, so it must be the strongest
        # authority. This asserts the kernel produced meaningful (not flat)
        # scores rather than just exercising the import.
        scores = compute(_triangle())

        ranked = top_authorities(scores, k=3)
        self.assertEqual(ranked[0][0], 3)
        # Hubs: node 1 fans out to both 2 and 3, so it should lead the hubs.
        self.assertEqual(top_hubs(scores, k=1)[0][0], 1)

    def test_unnormalized_scales_each_vector_to_max_one(self) -> None:
        # normalized=False re-runs through line 112 too, then re-scales so the
        # max entry of each vector is 1.0 (Kleinberg's L-infinity form).
        scores = compute(_triangle(), normalized=False)

        self.assertAlmostEqual(max(scores.authority.values()), 1.0, places=6)
        self.assertAlmostEqual(max(scores.hub.values()), 1.0, places=6)
