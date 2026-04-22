"""Cascade Click Model — Craswell, Zoeter, Taylor, Ramsey (2008, WSDM).

Reference
---------
Craswell, N., Zoeter, O., Taylor, M. & Ramsey, B. (2008). "An
experimental comparison of click position-bias models." *WSDM*,
pp. 87-94.

Goal
----
A click-log row like ``query=foo, displayed=[A, B, C, D], clicked=C``
hides the fact that the user almost certainly read A and B, saw they
weren't what they wanted, read C, clicked, and **never looked at D**.
If we just treat "clicked" as a positive and "not clicked" as a
negative, we will score D as unambiguously bad — which is wrong,
because the user never examined it.

The Cascade model formalises the behaviour:

- User scans from position 1 downward.
- At each position ``i`` with relevance ``r_i``, the user clicks with
  probability ``r_i``. If they click, they stop reading.
- If they don't click, they continue to position ``i + 1``.

Given a session with clicked rank ``c`` (``c = None`` if no click),
this module:

1. Marks positions ``1..c-1`` as **examined + not clicked** (negative
   evidence for their relevance).
2. Marks position ``c`` (if any) as **examined + clicked** (positive
   evidence).
3. Marks positions ``c+1..end`` as **unexamined** (no evidence).

The MLE for each doc's relevance then becomes::

    r_d = clicks_on_d / examinations_of_d

with Laplace smoothing so items shown only once or twice don't
explode toward 0 or 1.

This is pure arithmetic — the caller hands in the click logs, this
module returns per-doc relevance estimates. A scheduled "cascade
click EM re-estimate" job runs this weekly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence


#: Laplace smoothing — ``(clicks + α) / (examinations + α + β)``.
#: α = 1, β = 1 means the prior is "equal chance of click or no click"
#: which keeps low-exposure items near the 0.5 mean.
DEFAULT_PRIOR_ALPHA: float = 1.0
DEFAULT_PRIOR_BETA: float = 1.0


@dataclass(frozen=True)
class ClickSession:
    """One displayed result list plus the observed click (if any).

    ``ranked_docs`` is the ordered list the user saw (position 1 is
    the top). ``clicked_rank`` is the 1-based position of the click,
    or ``None`` if the user left without clicking. Cascade assumes
    at most one click per session.
    """

    ranked_docs: Sequence[Hashable]
    clicked_rank: int | None


@dataclass(frozen=True)
class DocRelevance:
    """Per-doc Cascade-model estimate."""

    doc_id: Hashable
    relevance: float
    examinations: int     # times the user reached this doc
    clicks: int           # times the user clicked this doc


def estimate(
    sessions: Iterable[ClickSession],
    *,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
) -> dict[Hashable, DocRelevance]:
    """Return Cascade-model relevance for every doc in *sessions*.

    Missing docs (never examined) are not in the output — the caller
    can treat their relevance as the prior mean ``α / (α + β)``.

    Raises
    ------
    ValueError
        If a session declares a click at a rank beyond the displayed
        list, or if the priors are non-positive.
    """
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("priors must be > 0")

    examinations: dict[Hashable, int] = {}
    clicks: dict[Hashable, int] = {}

    for session in sessions:
        docs = list(session.ranked_docs)
        if not docs:
            continue
        clicked = session.clicked_rank
        if clicked is not None and not 1 <= clicked <= len(docs):
            raise ValueError(
                f"clicked_rank {clicked} out of range for a list of "
                f"{len(docs)} docs"
            )
        examined_depth = clicked if clicked is not None else len(docs)
        for position_1based, doc_id in enumerate(docs[:examined_depth], start=1):
            examinations[doc_id] = examinations.get(doc_id, 0) + 1
            if clicked is not None and position_1based == clicked:
                clicks[doc_id] = clicks.get(doc_id, 0) + 1

    out: dict[Hashable, DocRelevance] = {}
    for doc_id, n_exam in examinations.items():
        n_click = clicks.get(doc_id, 0)
        smoothed = (n_click + prior_alpha) / (n_exam + prior_alpha + prior_beta)
        out[doc_id] = DocRelevance(
            doc_id=doc_id,
            relevance=smoothed,
            examinations=n_exam,
            clicks=n_click,
        )
    return out


def prior_mean(
    *,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
) -> float:
    """Return ``α / (α + β)`` — the prior relevance for never-seen docs."""
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("priors must be > 0")
    return prior_alpha / (prior_alpha + prior_beta)
