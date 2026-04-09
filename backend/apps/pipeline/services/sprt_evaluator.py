"""
Sequential Probability Ratio Test (SPRT) for weight challenger evaluation.

Replaces the simple 1.05x threshold check with a statistically principled
decision boundary that controls both Type I (false promotion) and Type II
(false rejection) error rates.
"""

from __future__ import annotations

import math
from typing import NamedTuple


class SPRTResult(NamedTuple):
    decision: str  # "promote", "reject", or "continue"
    log_likelihood_ratio: float
    upper_boundary: float  # log((1-beta)/alpha)
    lower_boundary: float  # log(beta/(1-alpha))


class ChallengerSPRTEvaluator:
    """
    SPRT evaluator for ranking weight challengers.

    H0 (champion): challenger quality <= champion quality
    H1 (challenger): challenger quality > champion quality by >= min_improvement_ratio

    Parameters
    ----------
    alpha : float
        Type I error rate (false promotion). Default 0.05 (5%).
    beta : float
        Type II error rate (false rejection). Default 0.10 (10%).
    min_improvement_ratio : float
        Minimum relative improvement required for promotion. Default 1.05 (5%).
    assumed_std_dev : float
        Assumed standard deviation of quality scores. Default 0.08 (8%).
    """

    def __init__(
        self,
        alpha: float = 0.05,
        beta: float = 0.10,
        min_improvement_ratio: float = 1.05,
        assumed_std_dev: float = 0.08,
    ):
        self.alpha = alpha
        self.beta = beta
        self.sigma = assumed_std_dev
        self.delta = math.log(min_improvement_ratio)

        # Wald boundaries
        self.upper = math.log((1 - beta) / alpha)
        self.lower = math.log(beta / (1 - alpha))

    def evaluate(
        self,
        challenger_score: float,
        champion_score: float,
    ) -> SPRTResult:
        """Run SPRT on observed quality scores."""
        diff = challenger_score - champion_score

        # Log-likelihood ratio (normal approximation)
        lr = (diff - self.delta / 2) * self.delta / (self.sigma ** 2)

        if lr >= self.upper:
            decision = "promote"
        elif lr <= self.lower:
            decision = "reject"
        else:
            decision = "continue"

        return SPRTResult(
            decision=decision,
            log_likelihood_ratio=round(lr, 4),
            upper_boundary=round(self.upper, 4),
            lower_boundary=round(self.lower, 4),
        )
