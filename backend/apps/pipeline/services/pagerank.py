"""Compatibility wrapper for the March 2026 PageRank service."""

from .weighted_pagerank import (
    WeightedLoadedGraph as LoadedGraph,
    calculate_weighted_pagerank as calculate_pagerank,
    load_weighted_graph as load_graph,
    persist_weighted_pagerank as persist_pagerank,
    run_weighted_pagerank as run_pagerank,
)
