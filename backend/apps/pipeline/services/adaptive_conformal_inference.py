"""Adaptive Conformal Inference — Gibbs & Candès (NeurIPS 2021).

Reference
---------
Gibbs, I. & Candès, E. J. (2021). "Adaptive Conformal Inference Under
Distribution Shift." *NeurIPS*. <https://arxiv.org/abs/2106.00170>.

Goal
----
Plain split-conformal prediction (pick #50) assumes exchangeability —
the calibration distribution matches the test distribution. Real-world
data drifts. ACI watches observed coverage online and nudges ``α`` up
when coverage drops below the target or down when coverage exceeds it.
Long-run coverage converges to the target with zero distributional
assumptions — Gibbs-Candès prove it via Algorithm 1.

Algorithm 1 in one line::

    α_{t+1} = clip( α_t + γ · (target_α − observed_miscoverage_t),
                    clip_min, clip_max )

where ``observed_miscoverage_t`` is the fraction of the last
``window_size`` predictions whose true label landed *outside* the
conformal interval.

Safety rails
------------
Paper's raw algorithm lets α drift arbitrarily. We clip to
``[clip_alpha_min, clip_alpha_max]`` (defaults 0.01 and 0.50) so one
adversarial streak can't push α to a pathological value.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


#: 90 % coverage target — matches pick-50 Conformal Prediction default.
DEFAULT_TARGET_ALPHA: float = 0.10

#: Gibbs-Candès Algorithm 1 recommended range: 0.005 – 0.05. We pick
#: 0.005 — slower adaptation, lower variance under noisy coverage
#: estimates. TPE-tuned within the paper's range.
DEFAULT_LEARNING_RATE_GAMMA: float = 0.005

#: Rolling window of recent (prediction, outcome) pairs used to
#: estimate observed miscoverage. Gibbs-Candès §4 shows larger
#: windows reduce variance; smaller windows react faster. 500 is the
#: plan-spec balance.
DEFAULT_WINDOW_SIZE: int = 500

#: Floor — never push α below 1 % miscoverage (would make intervals
#: unbearably wide in a noisy regime).
DEFAULT_CLIP_MIN: float = 0.01

#: Ceiling — never push α above 50 % (above this, intervals provide
#: no useful information).
DEFAULT_CLIP_MAX: float = 0.50


@dataclass
class AdaptiveConformalInference:
    """Stateful ACI updater.

    Feed coverage outcomes via :meth:`update`; read the adapted α via
    :attr:`current_alpha`. The object is **mutable** so operators can
    pickle-save / reload the state across process restarts without
    losing the learning-rate trajectory.
    """

    target_alpha: float = DEFAULT_TARGET_ALPHA
    learning_rate_gamma: float = DEFAULT_LEARNING_RATE_GAMMA
    window_size: int = DEFAULT_WINDOW_SIZE
    clip_min: float = DEFAULT_CLIP_MIN
    clip_max: float = DEFAULT_CLIP_MAX

    current_alpha: float = field(init=False)
    _window: deque = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.0 < self.target_alpha < 1.0:
            raise ValueError("target_alpha must be in (0, 1)")
        if self.learning_rate_gamma <= 0.0:
            raise ValueError("learning_rate_gamma must be > 0")
        if self.window_size <= 0:
            raise ValueError("window_size must be > 0")
        if not 0.0 < self.clip_min < self.clip_max < 1.0:
            raise ValueError("clip bounds must satisfy 0 < clip_min < clip_max < 1")
        if not self.clip_min <= self.target_alpha <= self.clip_max:
            raise ValueError("target_alpha must fall within [clip_min, clip_max]")

        self.current_alpha = self.target_alpha
        self._window = deque(maxlen=self.window_size)

    # ── Public API ────────────────────────────────────────────────

    def update(self, was_covered: bool) -> float:
        """Feed one observation and return the updated α.

        Warmup: while the window has fewer than half its capacity of
        observations, we keep α at the target to avoid flapping on
        tiny samples.
        """
        self._window.append(1.0 if was_covered else 0.0)
        if len(self._window) < max(1, self.window_size // 2):
            return self.current_alpha

        observed_coverage = sum(self._window) / len(self._window)
        observed_miscoverage = 1.0 - observed_coverage
        delta = observed_miscoverage - self.target_alpha
        # α_{t+1} = α_t + γ · (observed − target). If we're
        # *under*-covering (miscov > target), α needs to grow to widen
        # intervals. If *over*-covering, α shrinks.
        next_alpha = self.current_alpha + self.learning_rate_gamma * delta
        self.current_alpha = max(self.clip_min, min(self.clip_max, next_alpha))
        return self.current_alpha

    @property
    def observations(self) -> int:
        """Number of outcomes fed so far (capped at ``window_size``)."""
        return len(self._window)

    @property
    def observed_coverage(self) -> float:
        """Fraction of recent predictions whose true labels were in-band."""
        if not self._window:
            return 0.0
        return sum(self._window) / len(self._window)

    def snapshot(self) -> dict[str, float]:
        """Return a JSON-serialisable snapshot for persistence."""
        return {
            "target_alpha": self.target_alpha,
            "current_alpha": self.current_alpha,
            "learning_rate_gamma": self.learning_rate_gamma,
            "window_size": float(self.window_size),
            "observations": float(len(self._window)),
            "observed_coverage": self.observed_coverage,
        }
