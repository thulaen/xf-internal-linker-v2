"""Cosine annealing learning-rate schedule — pick #43.

Reference
---------
Loshchilov, I. & Hutter, F. (2017). "SGDR: Stochastic Gradient
Descent with Warm Restarts." *International Conference on Learning
Representations (ICLR) 2017*.

Goal
----
At training step ``t`` within a cycle of length ``T``, the learning
rate is set to::

    lr(t) = lr_min + 0.5 * (lr_max - lr_min) * (1 + cos(π * t / T))

This is a smooth half-cosine curve from ``lr_max`` down to
``lr_min`` — empirically beats step-decay and exponential-decay on
most deep-learning workloads. The "warm restarts" extension simply
restarts the curve every ``T`` steps.

This module is a pure-stdlib implementation. No torch dependency at
the helper layer (the torch ``CosineAnnealingWarmRestarts`` does
the same math); training code that uses torch can still construct
its own scheduler — this helper is for downstream callers that need
the LR value at step ``t`` without instantiating a torch optimiser.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CosineAnnealingSchedule:
    """Configuration for the cosine schedule + restarts."""

    lr_max: float
    lr_min: float
    cycle_length: int  # T — steps per cycle (paper's T_i)
    cycle_multiplier: float = 1.0  # T_mult — multiply T after each restart


def learning_rate_at_step(
    step: int,
    schedule: CosineAnnealingSchedule,
) -> float:
    """Return the LR at training step *step*.

    Step 0 returns ``lr_max``; step ``cycle_length`` returns
    ``lr_min``; afterwards the schedule restarts (with cycle length
    multiplied by ``cycle_multiplier``).

    Cold-start safe: invalid configs (negative cycle, zero
    multiplier) fall back to ``lr_max`` rather than divide-by-zero.
    """
    if schedule.cycle_length <= 0 or schedule.cycle_multiplier <= 0:
        return float(schedule.lr_max)

    # Find the cycle this step is in. Each subsequent cycle length
    # multiplies by cycle_multiplier per Loshchilov-Hutter §3.1.
    remaining = step
    current_T = schedule.cycle_length
    while remaining >= current_T:
        remaining -= current_T
        current_T = max(1, int(current_T * schedule.cycle_multiplier))

    # Within-cycle cosine.
    progress = remaining / max(1, current_T)
    cosine_term = 0.5 * (1.0 + math.cos(math.pi * progress))
    return float(schedule.lr_min + (schedule.lr_max - schedule.lr_min) * cosine_term)
