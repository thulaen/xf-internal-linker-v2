"""CUDA-accelerated random-walk kernels (masterplan Group C).

Plain-English purpose: PageRank, Personalized PageRank, and HITS are
sparse-matrix-times-vector loops at their core. The existing C++
kernel in ``backend/extensions/pagerank.cpp`` runs them on the CPU
via TBB; this module provides CUDA-equivalent paths via cuPy +
cuSPARSE so the daily PR / HITS / TrustRank chain finishes in
~1–2 minutes instead of ~18.

Numerical contract: each function in this module produces the same
output as its C++ counterpart within float64 round-off tolerance
(parity tests in ``test_pagerank_cuda_parity.py`` enforce
``abs ≤ 1e-5`` or ``rel ≤ 1e-6``). Different summation order on the
GPU means individual ranks may shift by ~1e-7; the test thresholds
absorb that without false alarms.

Fallback contract: if cuPy is missing OR ``torch.cuda.is_available()``
is False at call time, the functions raise ``CudaUnavailableError``
so the wrapper layer (``personalized_pagerank.py`` etc.) can fall
back to the existing C++ kernel cleanly. Failures during the actual
GPU work raise the underlying cuPy exception so the wrapper can log
+ fall back per Group C.5.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CudaUnavailableError(RuntimeError):
    """Raised when the cuPy / CUDA path can't run on this host.

    Wrappers translate this into a CPU-fallback dispatch. Message
    includes the specific reason (no torch, no cuPy, no GPU) so the
    operator's audit-log entry tells them exactly what to fix.
    """


def _require_cupy():
    """Lazy-import cuPy + cuSPARSE; raise ``CudaUnavailableError`` if unavailable.

    Defers the import so the module loads cleanly even on a CPU-only
    box. Lazy import lets the parity tests skip cleanly when run on a
    laptop without CUDA.
    """
    try:
        import torch
    except ImportError as exc:
        raise CudaUnavailableError(
            "PyTorch is not installed; cannot probe CUDA"
        ) from exc
    if not torch.cuda.is_available():
        raise CudaUnavailableError(
            "torch.cuda.is_available() is False — no GPU detected"
        )
    try:
        import cupy as cp  # noqa: F401 — proves the wheel is importable
        from cupyx.scipy import sparse as cp_sparse  # noqa: F401
    except ImportError as exc:
        raise CudaUnavailableError(
            "cupy-cuda12x is not installed; pip-install before retrying"
        ) from exc
    return cp, cp_sparse


def pagerank_step_cuda(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling_mask: np.ndarray,
    damping: float,
    node_count: int,
) -> Tuple[np.ndarray, float]:
    """One PageRank iteration on the GPU. Same math as ``pagerank_step_core``.

    Returns ``(next_ranks, delta)`` where ``delta`` is the L1 norm of
    ``|next_ranks - ranks|``. Caller iterates until ``delta`` falls
    below the convergence tolerance.
    """
    if node_count <= 0:
        return np.array([], dtype=np.float64), 0.0

    cp, cp_sparse = _require_cupy()

    # Convert CSR triplet to a GPU sparse matrix. CSR convention here
    # mirrors the C++ kernel: ``row = target``, ``col = source``,
    # ``A[row, col]`` weight means edge ``col → row``.
    A = cp_sparse.csr_matrix(
        (
            cp.asarray(data, dtype=cp.float64),
            cp.asarray(indices, dtype=cp.int32),
            cp.asarray(indptr, dtype=cp.int32),
        ),
        shape=(node_count, node_count),
    )
    ranks_gpu = cp.asarray(ranks, dtype=cp.float64)
    dangling_gpu = cp.asarray(dangling_mask, dtype=cp.bool_)

    # link_mass[row] = Σ A[row, col] * ranks[col]  ← cuSPARSE SpMV.
    link_mass = A.dot(ranks_gpu)
    next_ranks = (1.0 - damping) * link_mass

    # Sum of ranks for dangling rows; compiled into a single reduction.
    dangling_mass = float(cp.sum(ranks_gpu[dangling_gpu]))

    base_mass = ((1.0 - damping) * dangling_mass + damping) / node_count
    next_ranks = next_ranks + base_mass

    total_mass = float(cp.sum(next_ranks))
    if total_mass > 0.0:
        next_ranks = next_ranks / total_mass

    delta = float(cp.sum(cp.abs(next_ranks - ranks_gpu)))
    return cp.asnumpy(next_ranks), delta


def personalized_pagerank_step_cuda(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling_mask: np.ndarray,
    personalization: np.ndarray,
    damping: float,
    node_count: int,
) -> Tuple[np.ndarray, float]:
    """One Personalized PageRank iteration on the GPU.

    Mirrors ``personalized_pagerank_step_core``: the teleport mass is
    distributed by the per-node personalisation vector (Haveliwala
    2002 §3) instead of uniformly.
    """
    if node_count <= 0:
        return np.array([], dtype=np.float64), 0.0

    cp, cp_sparse = _require_cupy()

    A = cp_sparse.csr_matrix(
        (
            cp.asarray(data, dtype=cp.float64),
            cp.asarray(indices, dtype=cp.int32),
            cp.asarray(indptr, dtype=cp.int32),
        ),
        shape=(node_count, node_count),
    )
    ranks_gpu = cp.asarray(ranks, dtype=cp.float64)
    dangling_gpu = cp.asarray(dangling_mask, dtype=cp.bool_)
    personalization_gpu = cp.asarray(personalization, dtype=cp.float64)

    link_mass = A.dot(ranks_gpu)
    next_ranks = (1.0 - damping) * link_mass

    dangling_mass = float(cp.sum(ranks_gpu[dangling_gpu]))
    teleport_mass = (1.0 - damping) * dangling_mass + damping
    next_ranks = next_ranks + teleport_mass * personalization_gpu

    total_mass = float(cp.sum(next_ranks))
    if total_mass > 0.0:
        next_ranks = next_ranks / total_mass

    delta = float(cp.sum(cp.abs(next_ranks - ranks_gpu)))
    return cp.asnumpy(next_ranks), delta


def hits_step_cuda(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    authority: np.ndarray,
    hub: np.ndarray,
    node_count: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """One HITS iteration on the GPU. Same math as ``hits_step_core``.

    Two SpMV calls per iteration:
    * ``next_authority = A · hub`` — for each edge u→v of weight w,
      v's authority gets +w*hub[u].
    * ``next_hub = Aᵀ · authority`` — for the same edge, u's hub
      gets +w*authority[v].

    Normalisation + convergence checks happen in the Python driver,
    matching the C++ contract.
    """
    if node_count <= 0:
        empty = np.array([], dtype=np.float64)
        return empty, empty

    cp, cp_sparse = _require_cupy()

    A = cp_sparse.csr_matrix(
        (
            cp.asarray(data, dtype=cp.float64),
            cp.asarray(indices, dtype=cp.int32),
            cp.asarray(indptr, dtype=cp.int32),
        ),
        shape=(node_count, node_count),
    )
    authority_gpu = cp.asarray(authority, dtype=cp.float64)
    hub_gpu = cp.asarray(hub, dtype=cp.float64)

    next_authority = A.dot(hub_gpu)
    # CSR's transpose-then-dot is implemented internally as CSC SpMV
    # by cuSPARSE — single GPU op, no host round-trip.
    next_hub = A.T.dot(authority_gpu)

    return cp.asnumpy(next_authority), cp.asnumpy(next_hub)


def cuda_random_walk_available() -> bool:
    """Cheap probe — True iff this module can run a kernel on the GPU.

    Wrappers call this once per dispatch instead of catching
    ``CudaUnavailableError`` from inside a hot loop.
    """
    try:
        _require_cupy()
        return True
    except CudaUnavailableError:
        return False
    except Exception:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.  # pragma: no cover — defensive
        return False


# ---------------------------------------------------------------------------
# Group C.5 — Safe CUDA dispatchers with /error-log routing + CPU fallback.
#
# Each function below tries the CUDA path first. If cuPy / CUDA isn't
# available on this host (``CudaUnavailableError``), it silently falls
# back to the supplied CPU function — that's an expected system state,
# not an error. If the CUDA call raises any OTHER exception (kernel
# launch failure, OOM, driver bug), we log to ``/error-log`` ONCE per
# process via a module-level flag and fall back to CPU for the rest of
# this run. Subsequent calls skip the CUDA attempt entirely so a flaky
# GPU can't spam the audit log.
#
# Callers don't need to know any of this — they just call the safe
# function with the same arguments they'd give the C++ kernel plus a
# ``fallback_cpu_fn`` that takes the same arguments and returns the
# same shape. Drop-in replacement for the existing ``pagerank_kernel.*``
# calls in personalized_pagerank.py / hits.py / trustrank.py.
# ---------------------------------------------------------------------------

_CUDA_DISABLED_THIS_PROCESS: bool = False


def _record_cuda_failure_once(*, step: str, exc: BaseException) -> None:
    """Log a CUDA failure to /error-log on first occurrence per process.

    Sets ``_CUDA_DISABLED_THIS_PROCESS = True`` so the safe dispatchers
    skip CUDA for the rest of the process — one row per kernel-step on
    the deduped errors page, not one per iteration.
    """
    global _CUDA_DISABLED_THIS_PROCESS
    already_disabled = _CUDA_DISABLED_THIS_PROCESS
    _CUDA_DISABLED_THIS_PROCESS = True
    if already_disabled:
        return
    try:
        import traceback

        from apps.audit.error_ingest import ingest_error
        from apps.audit.models import ErrorLog

        ingest_error(
            job_type="cuda_random_walk",
            step=step,
            error_message=str(exc) or exc.__class__.__name__,
            raw_exception=traceback.format_exc(),
            why=(
                "The CUDA random-walk path raised an unexpected exception. "
                "The pipeline fell back to the CPU C++ kernel for the rest "
                "of this process — suggestions still work, just slower. "
                "Restart the worker after fixing to re-enable CUDA."
            ),
            severity=ErrorLog.SEVERITY_HIGH,
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "CUDA random-walk failed (%s) AND audit-log path is broken", step
        )


def pagerank_step_safe(
    *,
    fallback_cpu_fn,
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling_mask: np.ndarray,
    damping: float,
    node_count: int,
) -> Tuple[np.ndarray, float]:
    """CUDA-first dispatcher for the basic PageRank step (Group C.5)."""
    if not _CUDA_DISABLED_THIS_PROCESS:
        try:
            return pagerank_step_cuda(
                indptr, indices, data, ranks, dangling_mask, damping, node_count
            )
        except CudaUnavailableError:
            # System state, not an error.
            pass
        except Exception as exc:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
            _record_cuda_failure_once(step="pagerank_step", exc=exc)
    return fallback_cpu_fn(
        indptr, indices, data, ranks, dangling_mask, damping, node_count
    )


def personalized_pagerank_step_safe(
    *,
    fallback_cpu_fn,
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling_mask: np.ndarray,
    personalization: np.ndarray,
    damping: float,
    node_count: int,
) -> Tuple[np.ndarray, float]:
    """CUDA-first dispatcher for Personalized PageRank (Group C.5)."""
    if not _CUDA_DISABLED_THIS_PROCESS:
        try:
            return personalized_pagerank_step_cuda(
                indptr,
                indices,
                data,
                ranks,
                dangling_mask,
                personalization,
                damping,
                node_count,
            )
        except CudaUnavailableError:
            pass  # intentional fallthrough — drop to the CPU branch below
        except Exception as exc:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
            _record_cuda_failure_once(step="personalized_pagerank_step", exc=exc)
    return fallback_cpu_fn(
        indptr,
        indices,
        data,
        ranks,
        dangling_mask,
        personalization,
        damping,
        node_count,
    )


def hits_step_safe(
    *,
    fallback_cpu_fn,
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    authority: np.ndarray,
    hub: np.ndarray,
    node_count: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """CUDA-first dispatcher for the HITS step (Group C.5)."""
    if not _CUDA_DISABLED_THIS_PROCESS:
        try:
            return hits_step_cuda(indptr, indices, data, authority, hub, node_count)
        except CudaUnavailableError:
            pass  # intentional fallthrough — drop to the CPU branch below
        except Exception as exc:  # noqa: BLE001  # Best-effort fallback in service/helper code; downstream code logs / returns a safe default — must not raise to the pipeline orchestrator.
            _record_cuda_failure_once(step="hits_step", exc=exc)
    return fallback_cpu_fn(indptr, indices, data, authority, hub, node_count)
