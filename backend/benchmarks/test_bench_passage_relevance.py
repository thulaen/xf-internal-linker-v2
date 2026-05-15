"""Three-size benchmark for FR-053 passage relevance scoring.

Plain-English purpose: prove the per-host, per-destination cosine
operation stays inside its hot-path budget on the target machine.
The production path uses the Docker-built C++ ``passagesim`` dynamic
library when it is available. Python remains a correctness reference.

Three input sizes:
  - Small  =   50 candidates x 5 passages  =   250 passage embeddings
  - Medium =  500 candidates x 5 passages  = 2,500 passage embeddings
  - Large  = 5000 candidates x 5 passages  = 25,000 passage embeddings
"""

from __future__ import annotations

from functools import cache
import time

import numpy as np
import pytest


_DIM = 1024
_PASSAGES_PER_DESTINATION = 5
_SIZES = (
    ("small_50", 50),
    ("medium_500", 500),
    ("large_5000", 5000),
)


def _load_passagesim():
    try:
        from extensions import passagesim
    except ImportError:
        pytest.skip("passagesim C++ kernel not built")
    return passagesim


def _make_random_unit_vectors(n: int, dim: int = _DIM, seed: int = 1234) -> np.ndarray:
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(size=(n, dim)).astype(np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return raw / norms


@cache
def _passage_cube(
    n_destinations: int,
    passages_per_destination: int = _PASSAGES_PER_DESTINATION,
) -> np.ndarray:
    total = n_destinations * passages_per_destination
    matrix = _make_random_unit_vectors(total)
    return np.ascontiguousarray(
        matrix.reshape(n_destinations, passages_per_destination, _DIM)
    )


@cache
def _query_vector() -> np.ndarray:
    return np.ascontiguousarray(_make_random_unit_vectors(1)[0])


def _python_maxsim_reference(
    query: np.ndarray, passage_matrix: np.ndarray
) -> tuple[float, int]:
    sims = passage_matrix @ query
    best_idx = int(np.argmax(sims))
    return float(sims[best_idx]), best_idx


def _run_cpp_batch(passagesim, query: np.ndarray, cube: np.ndarray) -> list[tuple[int, float]]:
    results = []
    for passage_matrix in cube:
        best_sim, best_idx = passagesim.maxsim(query, passage_matrix)
        results.append((int(best_idx), float(best_sim)))
    return results


def _run_python_reference_batch(
    query: np.ndarray, cube: np.ndarray
) -> list[tuple[int, float]]:
    results = []
    for passage_matrix in cube:
        best_sim, best_idx = _python_maxsim_reference(query, passage_matrix)
        results.append((best_idx, best_sim))
    return results


def test_passagesim_cpp_matches_python_reference():
    passagesim = _load_passagesim()
    query = _query_vector()
    cube = _passage_cube(8)

    for passage_matrix in cube:
        cpp_sim, cpp_idx = passagesim.maxsim(query, passage_matrix)
        py_sim, py_idx = _python_maxsim_reference(query, passage_matrix)

        assert int(cpp_idx) == py_idx
        assert float(cpp_sim) == pytest.approx(py_sim, abs=1e-5)


@pytest.mark.parametrize(("size_label", "n_candidates"), _SIZES)
def test_bench_passage_relevance_cpp_kernel(benchmark, size_label, n_candidates):
    passagesim = _load_passagesim()
    query = _query_vector()
    cube = _passage_cube(n_candidates)

    out = benchmark(_run_cpp_batch, passagesim, query, cube)

    assert len(out) == n_candidates


@pytest.mark.parametrize(("size_label", "n_candidates"), _SIZES)
def test_bench_passage_relevance_python_reference(benchmark, size_label, n_candidates):
    query = _query_vector()
    cube = _passage_cube(n_candidates)

    out = benchmark(_run_python_reference_batch, query, cube)

    assert len(out) == n_candidates


def test_passage_relevance_medium_batch_under_50ms():
    passagesim = _load_passagesim()
    query = _query_vector()
    cube = _passage_cube(500)

    _run_cpp_batch(passagesim, query, cube[:5])
    start = time.perf_counter()
    _run_cpp_batch(passagesim, query, cube)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 100.0, (
        f"C++ medium batch took {elapsed_ms:.1f} ms; "
        "the target budget is 50 ms and the hard guard is 100 ms."
    )
