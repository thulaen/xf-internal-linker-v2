"""Small health summaries for ranking signals shown on Diagnostics.

The helpers read recent ``Suggestion`` diagnostic blobs and report whether
each signal is producing real values or falling back to its neutral state.
They do not change ranking math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from django.utils import timezone

_WINDOW_DAYS = 7


@dataclass(frozen=True, slots=True)
class SignalHealthSpec:
    signal_id: str
    diagnostics_field: str
    neutral_checker: Callable[[dict[str, Any]], bool]


def _is_passage_neutral(diagnostics: dict[str, Any]) -> bool:
    state = str(diagnostics.get("passage_relevance_state") or "")
    return state.startswith("neutral_")


def _is_fallback_triggered(diagnostics: dict[str, Any]) -> bool:
    return bool(diagnostics.get("fallback_triggered"))


WAVE2_SIGNAL_HEALTH_SPECS: tuple[SignalHealthSpec, ...] = (
    SignalHealthSpec(
        signal_id="passage_relevance",
        diagnostics_field="passage_relevance_diagnostics",
        neutral_checker=_is_passage_neutral,
    ),
    SignalHealthSpec(
        signal_id="darb",
        diagnostics_field="darb_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="kmig",
        diagnostics_field="kmig_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="tapb",
        diagnostics_field="tapb_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="kcib",
        diagnostics_field="kcib_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="berp",
        diagnostics_field="berp_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="hgte",
        diagnostics_field="hgte_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
    SignalHealthSpec(
        signal_id="rsqva",
        diagnostics_field="rsqva_diagnostics",
        neutral_checker=_is_fallback_triggered,
    ),
)


def compute_wave2_signal_health() -> dict[str, dict[str, Any]]:
    """Return 7-day neutral-fallback health keyed by signal id."""

    from apps.suggestions.models import Suggestion

    since = timezone.now() - timedelta(days=_WINDOW_DAYS)
    fields = [spec.diagnostics_field for spec in WAVE2_SIGNAL_HEALTH_SPECS]
    rows = Suggestion.objects.filter(updated_at__gte=since).values_list(
        "updated_at",
        *fields,
    )
    summaries = {
        spec.signal_id: {
            "window_days": _WINDOW_DAYS,
            "sample_count": 0,
            "neutral_fallback_count": 0,
            "neutral_fallback_rate": None,
            "last_run_at": None,
            "status_label": "No recent diagnostics",
            "plain_english": (
                "No recent suggestion diagnostics were found for this signal."
            ),
        }
        for spec in WAVE2_SIGNAL_HEALTH_SPECS
    }

    for row in rows:
        updated_at = row[0]
        diagnostics_by_field = dict(zip(fields, row[1:], strict=True))
        for spec in WAVE2_SIGNAL_HEALTH_SPECS:
            diagnostics = diagnostics_by_field.get(spec.diagnostics_field)
            if not isinstance(diagnostics, dict) or not diagnostics:
                continue
            summary = summaries[spec.signal_id]
            summary["sample_count"] += 1
            if spec.neutral_checker(diagnostics):
                summary["neutral_fallback_count"] += 1
            current_last = summary["last_run_at"]
            if current_last is None or updated_at > current_last:
                summary["last_run_at"] = updated_at

    for summary in summaries.values():
        sample_count = int(summary["sample_count"])
        fallback_count = int(summary["neutral_fallback_count"])
        if sample_count == 0:
            continue
        rate = fallback_count / sample_count
        summary["neutral_fallback_rate"] = rate
        if fallback_count == 0:
            summary["status_label"] = "Using real signal data"
            summary["plain_english"] = (
                "Every recent diagnostic used real signal data instead of a "
                "neutral fallback."
            )
        else:
            summary["status_label"] = "Fallbacks seen"
            summary["plain_english"] = (
                f"{fallback_count} of {sample_count} recent diagnostics used "
                "the neutral fallback."
            )
        if summary["last_run_at"] is not None:
            summary["last_run_at"] = summary["last_run_at"].isoformat()

    return summaries
