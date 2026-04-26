"""L-BFGS-B — pick #41.

Reference
---------
Byrd, R. H., Lu, P., Nocedal, J., & Zhu, C. (1995). "A Limited
Memory Algorithm for Bound Constrained Optimization." *SIAM Journal
on Scientific Computing*, 16(5), 1190-1208.

L-BFGS-B is a quasi-Newton optimizer for smooth objective functions
with optional box constraints (lower/upper bounds per parameter).
Used by the weight-tuner to find the linear-blend coefficients that
maximise NDCG over the validation pool — with bounds keeping each
weight in ``[0, 1]``.

This wraps :func:`scipy.optimize.minimize` so callers don't need to
remember the ``method="L-BFGS-B"`` magic string and so we get a
typed result object back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class LbfgsBResult:
    """Outcome of a single L-BFGS-B run."""

    x: list[float]  # final parameter vector
    fun: float  # final objective value
    converged: bool  # scipy's ``success`` flag
    iterations: int  # iteration count
    message: str  # scipy's status message


def minimize_lbfgs_b(
    objective: Callable[[np.ndarray], float],
    *,
    x0: Sequence[float],
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
    max_iter: int = 200,
    tolerance: float = 1e-6,
    gradient: Callable[[np.ndarray], np.ndarray] | None = None,
) -> LbfgsBResult:
    """Run L-BFGS-B over *objective*.

    Parameters
    ----------
    objective
        Scalar function to minimise; takes a 1-D ``np.ndarray`` and
        returns a float.
    x0
        Starting parameter vector.
    bounds
        Optional list of ``(low, high)`` pairs (use ``None`` for
        unbounded sides).
    max_iter, tolerance
        Convergence controls passed straight to scipy.
    gradient
        Optional analytic gradient. ``None`` lets scipy use finite
        differences (slower but always works).

    Returns
    -------
    :class:`LbfgsBResult` — converged flag plus the final point.
    Cold-start safe: any scipy failure surfaces as
    ``converged=False`` with the error message; the caller can fall
    back to ``x0`` rather than crashing.
    """
    x0_array = np.asarray(x0, dtype=float)
    try:
        result = minimize(
            objective,
            x0_array,
            jac=gradient,
            method="L-BFGS-B",
            bounds=list(bounds) if bounds is not None else None,
            options={"maxiter": max_iter, "ftol": tolerance, "gtol": tolerance},
        )
    except Exception as exc:
        return LbfgsBResult(
            x=list(x0_array),
            fun=float("inf"),
            converged=False,
            iterations=0,
            message=f"scipy raised: {exc}",
        )
    return LbfgsBResult(
        x=[float(v) for v in result.x],
        fun=float(result.fun),
        converged=bool(result.success),
        iterations=int(getattr(result, "nit", 0)),
        message=str(getattr(result, "message", "")),
    )
