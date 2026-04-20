"""FR-045 anchor diversity and exact-match reuse guard.

Two execution paths share the arithmetic core:

- ``evaluate_anchor_diversity`` — per-candidate Python path used by the
  ranker loop. Unchanged signature since Phase 17; kept as the immediate
  reference.
- ``evaluate_anchor_diversity_batch`` — batch path that amortises the
  arithmetic across many candidates via the C++ fast path when the
  compiled extension is importable, else falls back to a Python loop
  driven by the same ``_compute_score_from_counts`` helper.

Both paths produce byte-identical diagnostics dicts because normalization
and ``round(..., 6)`` both stay in Python.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence, TypeAlias

try:
    # The C++ fast path (FR-045 batch scorer). Normalization and diagnostics
    # composition stay in Python; this module just delivers the arithmetic.
    from extensions import anchor_diversity as _anchor_diversity_cpp  # type: ignore

    HAS_CPP_EXT = True
except ImportError:
    _anchor_diversity_cpp = None  # type: ignore[assignment]
    HAS_CPP_EXT = False

ContentKey: TypeAlias = tuple[int, str]

ACTIVE_SUGGESTION_STATUSES = ("pending", "approved", "applied", "verified")
_NON_WORD_EDGE_RE = re.compile(r"^[^\w]+|[^\w]+$")
_WHITESPACE_RE = re.compile(r"\s+")

# State-index decoding for the C++ batch fast path. The integer values are
# a C++-internal encoding; this map is the single source of truth for the
# string keys written to ``anchor_diversity_diagnostics``. Do not renumber.
_STATE_BY_INDEX = {
    1: "neutral_no_history",
    2: "neutral_below_threshold",
    3: "penalized_exact_share",
    4: "penalized_exact_count",
    5: "blocked_exact_count",
}


@dataclass(frozen=True, slots=True)
class AnchorDiversitySettings:
    enabled: bool = True
    ranking_weight: float = 0.03
    min_history_count: int = 3
    max_exact_match_share: float = 0.40
    max_exact_match_count: int = 3
    hard_cap_enabled: bool = False
    algorithm_version: str = "fr045-v1"


@dataclass(frozen=True, slots=True)
class AnchorHistory:
    active_anchor_count: int
    exact_match_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class AnchorDiversityEvaluation:
    score_anchor_diversity: float
    score_component: float
    repeated_anchor: bool
    blocked: bool
    diagnostics: dict[str, object]


def normalize_anchor_text(raw: str) -> str:
    """Normalize anchor text for exact-surface reuse checks."""
    lowered = _WHITESPACE_RE.sub(" ", (raw or "").strip().lower())
    cleaned = _NON_WORD_EDGE_RE.sub("", lowered).strip()
    return cleaned


def build_anchor_history(
    rows: Iterable[tuple[ContentKey, str]],
) -> dict[ContentKey, AnchorHistory]:
    """Return active normalized-anchor counts grouped by destination."""
    counters: dict[ContentKey, Counter[str]] = defaultdict(Counter)
    totals: Counter[ContentKey] = Counter()

    for destination_key, raw_anchor in rows:
        normalized = normalize_anchor_text(raw_anchor)
        if not normalized:
            continue
        counters[destination_key][normalized] += 1
        totals[destination_key] += 1

    return {
        destination_key: AnchorHistory(
            active_anchor_count=int(totals[destination_key]),
            exact_match_counts=dict(counter),
        )
        for destination_key, counter in counters.items()
    }


def evaluate_anchor_diversity(
    *,
    destination_key: ContentKey,
    candidate_anchor_text: str,
    history_by_destination: Mapping[ContentKey, AnchorHistory],
    settings: AnchorDiversitySettings,
) -> AnchorDiversityEvaluation:
    """Evaluate exact-match anchor concentration for one destination."""
    normalized = normalize_anchor_text(candidate_anchor_text)
    history = history_by_destination.get(
        destination_key,
        AnchorHistory(active_anchor_count=0, exact_match_counts={}),
    )
    exact_match_count_before = int(history.exact_match_counts.get(normalized, 0))
    repeated_anchor = bool(normalized and exact_match_count_before > 0)

    diagnostics: dict[str, object] = {
        "normalized_anchor": normalized,
        "active_anchor_count": int(history.active_anchor_count),
        "exact_match_count_before": exact_match_count_before,
        "projected_exact_match_count": exact_match_count_before,
        "projected_exact_share": 0.0,
        "max_exact_match_share": settings.max_exact_match_share,
        "max_exact_match_count": settings.max_exact_match_count,
        "share_overflow": 0.0,
        "count_overflow_norm": 0.0,
        "spam_risk": 0.0,
        "score_anchor_diversity": 0.5,
        "hard_cap_enabled": settings.hard_cap_enabled,
        "would_block": False,
        "active_statuses_considered": list(ACTIVE_SUGGESTION_STATUSES),
        "algorithm_version": settings.algorithm_version,
    }

    if not settings.enabled:
        diagnostics["anchor_diversity_state"] = "disabled"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=repeated_anchor,
            blocked=False,
            diagnostics=diagnostics,
        )

    if not normalized:
        diagnostics["anchor_diversity_state"] = "neutral_no_anchor"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=False,
            blocked=False,
            diagnostics=diagnostics,
        )

    if history.active_anchor_count < settings.min_history_count:
        diagnostics["anchor_diversity_state"] = "neutral_no_history"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=repeated_anchor,
            blocked=False,
            diagnostics=diagnostics,
        )

    projected_exact_match_count = exact_match_count_before + 1
    projected_exact_share = projected_exact_match_count / max(
        history.active_anchor_count + 1,
        1,
    )
    share_overflow = max(
        0.0,
        projected_exact_share - settings.max_exact_match_share,
    ) / max(1.0 - settings.max_exact_match_share, 1e-9)
    count_overflow = max(
        0,
        projected_exact_match_count - settings.max_exact_match_count,
    )
    count_overflow_norm = min(
        1.0,
        count_overflow / max(settings.max_exact_match_count, 1),
    )
    spam_risk = min(1.0, 0.8 * share_overflow + 0.2 * count_overflow_norm)
    # FR-045 spec: neutral 0.5, lower means over-concentrated.
    score_anchor_diversity = 0.5 - 0.5 * spam_risk
    score_component = min(0.0, 2.0 * (score_anchor_diversity - 0.5))
    blocked = settings.hard_cap_enabled and (
        projected_exact_match_count > settings.max_exact_match_count
    )

    if blocked:
        state = "blocked_exact_count"
    elif count_overflow > 0:
        state = "penalized_exact_count"
    elif share_overflow > 0:
        state = "penalized_exact_share"
    else:
        state = "neutral_below_threshold"

    diagnostics.update(
        anchor_diversity_state=state,
        projected_exact_match_count=projected_exact_match_count,
        projected_exact_share=round(projected_exact_share, 6),
        share_overflow=round(share_overflow, 6),
        count_overflow_norm=round(count_overflow_norm, 6),
        spam_risk=round(spam_risk, 6),
        score_anchor_diversity=round(score_anchor_diversity, 6),
        would_block=blocked,
    )
    return AnchorDiversityEvaluation(
        score_anchor_diversity=score_anchor_diversity,
        score_component=score_component,
        repeated_anchor=repeated_anchor,
        blocked=blocked,
        diagnostics=diagnostics,
    )


def _build_diagnostics_base(
    normalized: str,
    history: AnchorHistory,
    exact_match_count_before: int,
    settings: AnchorDiversitySettings,
) -> dict[str, object]:
    """Initialise the diagnostics dict shared by both per-candidate and
    batch paths. Mirrors the dict built at line 123 of
    ``evaluate_anchor_diversity``.
    """
    return {
        "normalized_anchor": normalized,
        "active_anchor_count": int(history.active_anchor_count),
        "exact_match_count_before": exact_match_count_before,
        "projected_exact_match_count": exact_match_count_before,
        "projected_exact_share": 0.0,
        "max_exact_match_share": settings.max_exact_match_share,
        "max_exact_match_count": settings.max_exact_match_count,
        "share_overflow": 0.0,
        "count_overflow_norm": 0.0,
        "spam_risk": 0.0,
        "score_anchor_diversity": 0.5,
        "hard_cap_enabled": settings.hard_cap_enabled,
        "would_block": False,
        "active_statuses_considered": list(ACTIVE_SUGGESTION_STATUSES),
        "algorithm_version": settings.algorithm_version,
    }


def evaluate_anchor_diversity_batch(
    *,
    destination_keys: Sequence[ContentKey],
    candidate_anchor_texts: Sequence[str],
    history_by_destination: Mapping[ContentKey, AnchorHistory],
    settings: AnchorDiversitySettings,
) -> list[AnchorDiversityEvaluation]:
    """Batch FR-045 anchor diversity scorer.

    Delegates the arithmetic to the C++ extension when ``HAS_CPP_EXT`` is
    true (the preferred production path per BLC §2.3 for hot-path scoring
    loops); falls back to the per-candidate Python scorer otherwise. In
    both paths the diagnostics dict is composed in Python from
    byte-identical ingredients (normalization + ``round(..., 6)``), so the
    two paths are numerically indistinguishable at the serializer boundary.

    Parity guarantee: ``atol=1e-6, rtol=0`` on every numeric field (see
    ``backend/tests/test_parity_anchor_diversity.py``).
    """
    if len(destination_keys) != len(candidate_anchor_texts):
        raise ValueError(
            "destination_keys and candidate_anchor_texts must have equal length"
        )
    n = len(destination_keys)
    if n == 0:
        return []

    # Preamble — each entry computes the normalized anchor + looks up the
    # per-destination history. This is identical to the per-candidate path.
    normalized_anchors: list[str] = []
    histories: list[AnchorHistory] = []
    exact_before: list[int] = []
    for key, raw in zip(destination_keys, candidate_anchor_texts):
        norm = normalize_anchor_text(raw)
        normalized_anchors.append(norm)
        hist = history_by_destination.get(
            key, AnchorHistory(active_anchor_count=0, exact_match_counts={})
        )
        histories.append(hist)
        exact_before.append(int(hist.exact_match_counts.get(norm, 0)) if norm else 0)

    # Classify each candidate: which ones need arithmetic, which are
    # short-circuited by disabled / no-anchor / no-history?
    needs_math: list[int] = []
    for i in range(n):
        if not settings.enabled:
            continue
        if not normalized_anchors[i]:
            continue
        if histories[i].active_anchor_count < settings.min_history_count:
            continue
        needs_math.append(i)

    # Arithmetic results keyed by the original candidate index. Each slot
    # is either None (short-circuited case) or an 8-field dict.
    arithmetic: list[dict | None] = [None] * n
    if needs_math:
        computed = (
            _arithmetic_via_cpp(needs_math, histories, exact_before, settings)
            if HAS_CPP_EXT
            else _arithmetic_via_python(needs_math, histories, exact_before, settings)
        )
        for candidate_index, row in zip(needs_math, computed):
            arithmetic[candidate_index] = row

    # Compose evaluations in the same order as the inputs. Rounding happens
    # here (in Python) for byte-identical diagnostics JSON across both paths.
    runtime_path = "cpp" if HAS_CPP_EXT else "python"
    results: list[AnchorDiversityEvaluation] = []
    for i in range(n):
        norm = normalized_anchors[i]
        hist = histories[i]
        before = exact_before[i]
        repeated_anchor = bool(norm and before > 0)
        diagnostics = _build_diagnostics_base(norm, hist, before, settings)
        diagnostics["runtime_path"] = runtime_path

        if not settings.enabled:
            diagnostics["anchor_diversity_state"] = "disabled"
            results.append(
                AnchorDiversityEvaluation(
                    score_anchor_diversity=0.5,
                    score_component=0.0,
                    repeated_anchor=repeated_anchor,
                    blocked=False,
                    diagnostics=diagnostics,
                )
            )
            continue

        if not norm:
            diagnostics["anchor_diversity_state"] = "neutral_no_anchor"
            results.append(
                AnchorDiversityEvaluation(
                    score_anchor_diversity=0.5,
                    score_component=0.0,
                    repeated_anchor=False,
                    blocked=False,
                    diagnostics=diagnostics,
                )
            )
            continue

        if hist.active_anchor_count < settings.min_history_count:
            diagnostics["anchor_diversity_state"] = "neutral_no_history"
            results.append(
                AnchorDiversityEvaluation(
                    score_anchor_diversity=0.5,
                    score_component=0.0,
                    repeated_anchor=repeated_anchor,
                    blocked=False,
                    diagnostics=diagnostics,
                )
            )
            continue

        row = arithmetic[i]
        assert row is not None  # needs_math loop already filled this slot
        score = row["score"]
        score_component = min(0.0, 2.0 * (score - 0.5))
        diagnostics.update(
            anchor_diversity_state=_STATE_BY_INDEX.get(
                row["state_index"], "neutral_below_threshold"
            ),
            projected_exact_match_count=row["projected_count"],
            projected_exact_share=round(row["projected_share"], 6),
            share_overflow=round(row["share_overflow"], 6),
            count_overflow_norm=round(row["count_overflow_norm"], 6),
            spam_risk=round(row["spam_risk"], 6),
            score_anchor_diversity=round(score, 6),
            would_block=row["would_block"],
        )
        results.append(
            AnchorDiversityEvaluation(
                score_anchor_diversity=score,
                score_component=score_component,
                repeated_anchor=repeated_anchor,
                blocked=row["would_block"],
                diagnostics=diagnostics,
            )
        )

    return results


def _arithmetic_via_cpp(
    indices: list[int],
    histories: list[AnchorHistory],
    exact_before: list[int],
    settings: AnchorDiversitySettings,
) -> list[dict]:
    """Run the FR-045 arithmetic through the C++ batch scorer."""
    import numpy as np

    active = np.array(
        [histories[i].active_anchor_count for i in indices], dtype=np.int32
    )
    before = np.array([exact_before[i] for i in indices], dtype=np.int32)
    result = _anchor_diversity_cpp.evaluate_batch(  # type: ignore[union-attr]
        active,
        before,
        int(settings.min_history_count),
        float(settings.max_exact_match_share),
        int(settings.max_exact_match_count),
        bool(settings.hard_cap_enabled),
    )
    return [
        {
            "projected_count": int(result["projected_exact_count"][pos]),
            "projected_share": float(result["projected_exact_share"][pos]),
            "share_overflow": float(result["share_overflow"][pos]),
            "count_overflow_norm": float(result["count_overflow_norm"][pos]),
            "spam_risk": float(result["spam_risk"][pos]),
            "score": float(result["score_anchor_diversity"][pos]),
            "state_index": int(result["state_index"][pos]),
            "would_block": bool(result["would_block"][pos]),
        }
        for pos in range(len(indices))
    ]


def _arithmetic_via_python(
    indices: list[int],
    histories: list[AnchorHistory],
    exact_before: list[int],
    settings: AnchorDiversitySettings,
) -> list[dict]:
    """Pure-Python fallback mirroring ``evaluate_anchor_diversity_core`` in
    ``backend/extensions/anchor_diversity.cpp``. Used when the C++ extension
    is not compiled.
    """
    rows: list[dict] = []
    for candidate_index in indices:
        active = histories[candidate_index].active_anchor_count
        before = exact_before[candidate_index]
        projected_count = before + 1
        projected_share = projected_count / max(active + 1, 1)
        share_overflow = max(
            0.0, projected_share - settings.max_exact_match_share
        ) / max(1.0 - settings.max_exact_match_share, 1e-9)
        count_overflow = max(0, projected_count - settings.max_exact_match_count)
        count_overflow_norm = min(
            1.0, count_overflow / max(settings.max_exact_match_count, 1)
        )
        spam_risk = min(1.0, 0.8 * share_overflow + 0.2 * count_overflow_norm)
        score = 0.5 - 0.5 * spam_risk
        blocked = settings.hard_cap_enabled and (
            projected_count > settings.max_exact_match_count
        )
        if blocked:
            state_index = 5  # blocked_exact_count
        elif count_overflow > 0:
            state_index = 4  # penalized_exact_count
        elif share_overflow > 0:
            state_index = 3  # penalized_exact_share
        else:
            state_index = 2  # neutral_below_threshold
        rows.append(
            {
                "projected_count": projected_count,
                "projected_share": projected_share,
                "share_overflow": share_overflow,
                "count_overflow_norm": count_overflow_norm,
                "spam_risk": spam_risk,
                "score": score,
                "state_index": state_index,
                "would_block": blocked,
            }
        )
    return rows
