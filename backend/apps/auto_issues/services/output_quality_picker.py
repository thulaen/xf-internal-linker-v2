"""Output-quality probes → AutoIssue picker.

Closes Gap #8 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Catches
silent data-quality regressions: outputs that are wrong without crashing.
A bug that drops 30% of suggestions to score=0 raises no exception, no
slow query, no Pyroscope hot-spot — but it's a real production problem.

Each probe is a (label, callable, ok_threshold, severity) tuple. The
callable returns a numeric metric in [0, 1]; if it falls below
`ok_threshold` an AutoIssue is emitted.

Cross-source dedup via `services.dedup.upsert_dedup` per probe label.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _QualityProbe:
    label: str
    callable_path: str  # "module:function_name" so we can lazy-import
    ok_threshold: float  # metric must be >= this
    severity_when_below: str
    description: str


# Each probe returns a fraction in [0,1] representing "share of healthy
# rows". Falling below ok_threshold emits an AutoIssue. Lazy-imported
# via `_resolve_callable` so a probe whose target app isn't installed
# silently skips instead of crashing the whole picker.
_PROBES: tuple[_QualityProbe, ...] = (
    _QualityProbe(
        label="suggestion-non-zero-rate",
        callable_path="apps.auto_issues.services.output_quality_picker:_metric_suggestion_non_zero_rate",
        ok_threshold=0.85,
        severity_when_below=AutoIssue.SEVERITY_HIGH,
        description=(
            "Fraction of recent Suggestion rows with score > 0. A drop "
            "below 85% means the ranking pipeline is producing more "
            "zero-confidence rows than expected — usually a regression "
            "in feature extraction, embeddings, or the score formula."
        ),
    ),
    _QualityProbe(
        label="page-with-embedding-rate",
        callable_path="apps.auto_issues.services.output_quality_picker:_metric_page_embedding_coverage",
        ok_threshold=0.95,
        severity_when_below=AutoIssue.SEVERITY_HIGH,
        description=(
            "Fraction of Page rows with at least one embedding. Below "
            "95% means the embedding generator is failing for some "
            "pages — usually a tokenizer / spaCy model / GPU issue."
        ),
    ),
    _QualityProbe(
        label="errorlog-acknowledged-rate",
        callable_path="apps.auto_issues.services.output_quality_picker:_metric_errorlog_ack_rate",
        ok_threshold=0.30,
        severity_when_below=AutoIssue.SEVERITY_LOW,
        description=(
            "Fraction of unresolved-but-old ErrorLog rows that have been "
            "acknowledged by an operator. Below 30% means the team is "
            "letting the backlog grow. Low severity — informational."
        ),
    ),
)


# ── Metric callables ──────────────────────────────────────────────────────
# Each returns a float in [0, 1]. None means "skip — input doesn't exist
# yet" (don't penalise for missing data).


def _metric_suggestion_non_zero_rate() -> float | None:
    try:
        from apps.suggestions.models import Suggestion
    except ImportError:
        return None
    qs = Suggestion.objects.filter(
        created_at__gte=timezone.now() - timezone.timedelta(days=1)
    ) if hasattr(timezone, "timedelta") else Suggestion.objects.none()
    # `timezone.timedelta` doesn't exist; fall back to datetime.timedelta.
    from datetime import timedelta as _td
    qs = Suggestion.objects.filter(
        created_at__gte=timezone.now() - _td(days=1)
    )
    total = qs.count()
    if total < 50:
        return None  # insufficient sample
    non_zero = qs.exclude(score=0).count()
    return non_zero / total


def _metric_page_embedding_coverage() -> float | None:
    try:
        from apps.content.models import Page
    except ImportError:
        return None
    total = Page.objects.count()
    if total < 50:
        return None
    # Counts pages that have AT LEAST ONE embedding row associated.
    # The Page model exposes `has_embedding` on most schemas; if not,
    # this probe gracefully returns None.
    if not hasattr(Page, "has_embedding"):
        return None
    with_emb = Page.objects.filter(has_embedding=True).count()
    return with_emb / total


def _metric_errorlog_ack_rate() -> float | None:
    from datetime import timedelta as _td

    from apps.audit.models import ErrorLog

    week_old_cutoff = timezone.now() - _td(days=7)
    qs = ErrorLog.objects.filter(created_at__lt=week_old_cutoff)
    total = qs.count()
    if total < 20:
        return None
    acknowledged = qs.filter(acknowledged=True).count()
    return acknowledged / total


# ── Picker ────────────────────────────────────────────────────────────────


def _resolve_callable(path: str) -> Callable[[], float | None] | None:
    module_path, _, name = path.partition(":")
    try:
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, name, None)
    except Exception as exc:
        logger.warning("[output_quality_picker] cannot resolve %s: %s", path, exc)
        return None


def _upsert_quality_issue(probe: _QualityProbe, value: float) -> str:
    title = (
        f"Quality regression: {probe.label} = {value:.2f} "
        f"(threshold {probe.ok_threshold:.2f})"
    )
    description = (
        f"{probe.description}\n\n"
        f"Current value: {value:.4f}. Threshold: {probe.ok_threshold:.4f}. "
        f"Probes run daily; consult `source_observations` for trend. "
        f"If the value recovers above threshold the next run won't "
        f"re-promote (it'll be left as the existing row to acknowledge)."
    )
    canonical = canonical_fingerprint(f"quality::{probe.label}", "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"quality-{probe.label}",
        fingerprint=f"quality-{probe.label}",
        title=title,
        description=description,
        affected_files=[],
        severity=probe.severity_when_below,
        priority_score=0.65 if probe.severity_when_below == AutoIssue.SEVERITY_HIGH else 0.35,
        occurrence_count=1,
    )
    return outcome


def pick_output_quality() -> dict:
    """Run every probe; surface those below threshold as AutoIssues."""
    counts = {"created": 0, "merged": 0, "updated": 0, "ok": 0, "skipped": 0}
    for probe in _PROBES:
        fn = _resolve_callable(probe.callable_path)
        if fn is None:
            counts["skipped"] += 1
            continue
        try:
            value = fn()
        except Exception as exc:
            logger.warning(
                "[output_quality_picker] probe %s raised: %s", probe.label, exc
            )
            counts["skipped"] += 1
            continue
        if value is None:
            counts["skipped"] += 1
            continue
        if value >= probe.ok_threshold:
            counts["ok"] += 1
            continue
        outcome = _upsert_quality_issue(probe, value)
        counts[outcome] = counts.get(outcome, 0) + 1
    logger.info(
        "[auto_issues.output_quality_picker] probes=%d ok=%d skipped=%d created=%d merged=%d updated=%d",
        len(_PROBES), counts["ok"], counts["skipped"],
        counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "probes": len(_PROBES),
        "promoted": counts["created"] + counts["merged"] + counts["updated"],
        **counts,
    }
