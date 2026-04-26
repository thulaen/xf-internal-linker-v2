"""Collocation scoring via Pointwise Mutual Information (PMI).

Reference: Church & Hanks (1990). "Word association norms, mutual
information, and lexicography." *Computational Linguistics* 16(1):
22-29.

The existing ``apps.cooccurrence.services`` module implements Dunning's
log-likelihood-ratio (G²). PMI is a complementary statistic — G² is
better at handling small counts (it corrects for rare events), PMI is
better at surfacing genuinely associated pairs regardless of frequency.
Callers who want both ship both scores and let the ranker pick.

PMI(A, B) = log( P(A, B) / (P(A) * P(B)) )

Where P(X) is estimated from observed frequencies over N total
observations. Positive PMI means A and B co-occur more than chance,
negative PMI means less than chance, zero means independent.

Normalised PMI (NPMI) bounds the score to [-1, 1] which is easier to
threshold across corpora of very different sizes (Bouma 2009):

    NPMI(A, B) = PMI(A, B) / -log( P(A, B) )

Pure arithmetic. Does not implement collocation *discovery* (that's
:mod:`apps.cooccurrence`'s job). Given counts, returns scores.
"""

from __future__ import annotations

import math


#: The tiny probability floor below which we treat a pair as
#: effectively unobserved — log of zero is -inf, which propagates
#: through any comparison. We floor at this to keep arithmetic sane
#: without silently upgrading a pair we never actually saw.
_MIN_PROBABILITY: float = 1e-12


def pmi(
    *,
    joint_count: int,
    count_a: int,
    count_b: int,
    total: int,
) -> float:
    """Return PMI in base-2 for the pair (A, B).

    Base-2 means a PMI of 3.0 roughly corresponds to "A and B appear
    together 8× as often as chance would predict" — easier to reason
    about than natural log when tuning thresholds.

    Parameters
    ----------
    joint_count
        Number of observations containing BOTH A and B.
    count_a
        Number of observations containing A (at least once).
    count_b
        Number of observations containing B.
    total
        Grand total of observations in the corpus.

    Invariants
    ----------
    - Any count < 0 raises ``ValueError``.
    - ``total`` must be > 0.
    - ``joint_count`` cannot exceed either marginal.

    Returns ``-inf`` when ``joint_count`` is zero — the pair was
    never observed together, so "how associated are they" has no
    meaningful answer; the caller should filter those out or clip.
    """
    _guard_counts(joint_count, count_a, count_b, total)
    if joint_count == 0:
        return float("-inf")
    p_joint = max(joint_count / total, _MIN_PROBABILITY)
    p_a = max(count_a / total, _MIN_PROBABILITY)
    p_b = max(count_b / total, _MIN_PROBABILITY)
    return math.log2(p_joint / (p_a * p_b))


def normalised_pmi(
    *,
    joint_count: int,
    count_a: int,
    count_b: int,
    total: int,
) -> float:
    """Return Bouma-2009 NPMI in the range [-1.0, 1.0] (nat log).

    NPMI = PMI / -log(P(A, B)).

    Values:
      -  1.0  — always co-occur (maximum association)
      -  0.0  — independent
      - -1.0  — never co-occur (only possible if joint_count == 0 in
                 the limit; returns -1.0 directly in that case)

    Uses natural log internally; the normalisation by
    ``-log(P(joint))`` cancels the base, so the output is unitless.
    """
    _guard_counts(joint_count, count_a, count_b, total)
    if joint_count == 0:
        return -1.0
    p_joint = max(joint_count / total, _MIN_PROBABILITY)
    p_a = max(count_a / total, _MIN_PROBABILITY)
    p_b = max(count_b / total, _MIN_PROBABILITY)
    pmi_nat = math.log(p_joint / (p_a * p_b))
    denom = -math.log(p_joint)
    if denom <= 0:
        # P(joint) == 1 means the pair always co-occurs with
        # everything — degenerate; the Bouma formula is undefined.
        return 1.0
    return max(-1.0, min(1.0, pmi_nat / denom))


def _guard_counts(joint_count: int, count_a: int, count_b: int, total: int) -> None:
    if total <= 0:
        raise ValueError("total must be > 0")
    if joint_count < 0 or count_a < 0 or count_b < 0:
        raise ValueError("counts must be >= 0")
    if joint_count > count_a or joint_count > count_b:
        raise ValueError("joint_count cannot exceed either single-term marginal")
    if count_a > total or count_b > total:
        raise ValueError("single-term counts cannot exceed total")
