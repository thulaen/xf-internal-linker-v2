"""Verify a [REWRITE QUOTA EXEMPTION: ...] evidence file.

Implements the deterministic exemption release path from
docs/specs/fr-rewrite-quota-and-exemption.md. The command parses the
JSON evidence file, recomputes the projected-gain percentage, checks
the four conditions, and exits 0 only when all four hold.

Run:
    docker compose exec -T backend python manage.py verify_rewrite_exemption \\
        --area backend/apps/example \\
        --evidence-file docs/rewrite-evidence/session-2026-05-23.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError


# Default threshold for "tiny gain" verdict. The sticky body documents
# this as 30% (a rewrite is justified when the projected improvement
# is at least 30% on the named metric); per-session overrides land in
# the evidence file's `threshold_pct` field.
_DEFAULT_THRESHOLD_PCT = 30.0

# Tolerance for the recomputed-gain-vs-supplied-gain consistency check.
_GAIN_TOLERANCE_PCT = 0.01

# Python ML/AI islands declared in Sticky #1 (pipeline/ml/, embedding/,
# etc.). Files under these prefixes count as legitimate Python remains
# and do not count toward the rewrite-quota.
_PYTHON_ISLAND_PREFIXES = (
    "backend/apps/pipeline/ml/",
    "backend/apps/embedding/",
    "backend/apps/suggestions/ml/",
)


_REQUIRED_TOP_LEVEL_FIELDS = (
    "session_id",
    "touched_paths",
    "python_lines_remaining",
    "python_island_declared_in_sticky",
    "baseline",
    "projection",
    "citations",
)
_REQUIRED_BASELINE_FIELDS = (
    "metric",
    "value",
    "source",
    "function",
    "workload",
    "captured_at",
)
_REQUIRED_PROJECTION_FIELDS = (
    "method",
    "projected_value",
    "projected_gain_pct",
    "threshold_pct",
    "verdict",
)

_ACCEPTED_BASELINE_SOURCES = {"pyroscope", "otel_profiles", "benchmark"}
_ACCEPTED_PROJECTION_METHODS = {"model", "extrapolation", "prior_benchmark"}


def _missing_fields(payload: dict, required: tuple[str, ...]) -> list[str]:
    return [name for name in required if name not in payload]


def _python_islanded(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PYTHON_ISLAND_PREFIXES)


def _validate_baseline(baseline: dict) -> str | None:
    missing = _missing_fields(baseline, _REQUIRED_BASELINE_FIELDS)
    if missing:
        return f"baseline is missing fields: {', '.join(sorted(missing))}"
    if baseline["source"] not in _ACCEPTED_BASELINE_SOURCES:
        return (
            f"baseline.source must be one of "
            f"{sorted(_ACCEPTED_BASELINE_SOURCES)}; got {baseline['source']!r}"
        )
    try:
        value = float(baseline["value"])
    except (TypeError, ValueError):
        return f"baseline.value must be numeric; got {baseline['value']!r}"
    if value <= 0:
        return f"baseline.value must be positive; got {value}"
    return None


def _validate_projection(projection: dict) -> str | None:
    missing = _missing_fields(projection, _REQUIRED_PROJECTION_FIELDS)
    if missing:
        return f"projection is missing fields: {', '.join(sorted(missing))}"
    if projection["method"] not in _ACCEPTED_PROJECTION_METHODS:
        return (
            f"projection.method must be one of "
            f"{sorted(_ACCEPTED_PROJECTION_METHODS)}; got {projection['method']!r}"
        )
    try:
        float(projection["projected_value"])
        float(projection["projected_gain_pct"])
        float(projection["threshold_pct"])
    except (TypeError, ValueError):
        return "projection.projected_value, projected_gain_pct, threshold_pct must all be numeric"
    return None


def _recompute_gain_pct(baseline_value: float, projected_value: float) -> float:
    """Return (baseline - projected) / baseline * 100.0, rounded to 4 dp."""
    if baseline_value <= 0:
        return 0.0
    raw = (baseline_value - projected_value) / baseline_value * 100.0
    return round(raw, 4)


class Command(BaseCommand):
    """Verify a rewrite-quota exemption evidence file."""

    help = (
        "Verify a [REWRITE QUOTA EXEMPTION:] evidence file against the "
        "four conditions in docs/specs/fr-rewrite-quota-and-exemption.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--area",
            type=str,
            action="append",
            required=True,
            help="Repo-relative path the exemption claims (repeatable).",
        )
        parser.add_argument(
            "--evidence-file",
            type=str,
            required=True,
            help="Path to the JSON evidence file under docs/rewrite-evidence/.",
        )

    def handle(self, *args, **options) -> None:
        areas: list[str] = options["area"]
        evidence_path = Path(options["evidence_file"])

        if not evidence_path.is_file():
            raise CommandError(
                f"--evidence-file {evidence_path} does not exist or is "
                "not a file. The exemption requires a JSON evidence "
                "document under docs/rewrite-evidence/<session-id>.json."
            )

        try:
            payload: dict[str, Any] = json.loads(
                evidence_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise CommandError(
                f"--evidence-file {evidence_path} is not valid JSON: {exc}"
            ) from exc

        problems: list[str] = []

        # 1. Top-level shape.
        top_missing = _missing_fields(payload, _REQUIRED_TOP_LEVEL_FIELDS)
        if top_missing:
            problems.append(
                "evidence file is missing top-level fields: "
                f"{', '.join(sorted(top_missing))}"
            )

        # 2. Baseline.
        baseline = payload.get("baseline") or {}
        if isinstance(baseline, dict):
            baseline_problem = _validate_baseline(baseline)
            if baseline_problem:
                problems.append(baseline_problem)
        else:
            problems.append("baseline must be a JSON object")

        # 3. Projection.
        projection = payload.get("projection") or {}
        if isinstance(projection, dict):
            projection_problem = _validate_projection(projection)
            if projection_problem:
                problems.append(projection_problem)
        else:
            problems.append("projection must be a JSON object")

        # 4. Citations.
        citations = payload.get("citations") or []
        if not isinstance(citations, list) or not citations:
            problems.append(
                "citations must be a non-empty list of source identifiers"
            )

        # Stop here if structural validation failed; the arithmetic
        # check below assumes the fields are present and well-typed.
        if problems:
            raise CommandError(
                "rewrite-quota exemption refused: "
                + "; ".join(problems)
                + ". See docs/specs/fr-rewrite-quota-and-exemption.md "
                "for the schema."
            )

        # 5. Python remains in touched area.
        python_lines = int(payload["python_lines_remaining"])
        islanded = bool(payload["python_island_declared_in_sticky"])
        if python_lines > 0 and not islanded:
            non_islanded = [path for path in areas if not _python_islanded(path)]
            if non_islanded:
                raise CommandError(
                    f"rewrite-quota exemption refused: "
                    f"{python_lines} legacy Python lines remain in the "
                    f"touched areas {non_islanded} and the evidence does "
                    "not mark them as part of a declared ML/AI Python "
                    "island. Rewrite the remaining Python first."
                )

        # 6. Recomputed gain matches supplied gain.
        baseline_value = float(baseline["value"])
        projected_value = float(projection["projected_value"])
        supplied_gain = float(projection["projected_gain_pct"])
        threshold_pct = float(projection["threshold_pct"])
        recomputed = _recompute_gain_pct(baseline_value, projected_value)

        if abs(recomputed - supplied_gain) > _GAIN_TOLERANCE_PCT:
            raise CommandError(
                "rewrite-quota exemption refused: supplied "
                f"projected_gain_pct={supplied_gain} does not match the "
                f"recomputed value {recomputed} (baseline.value="
                f"{baseline_value}, projection.projected_value="
                f"{projected_value}). Recompute the gain and resubmit."
            )

        # 7. Gain is below threshold.
        if recomputed >= threshold_pct:
            raise CommandError(
                "rewrite-quota exemption refused: recomputed gain "
                f"{recomputed}% is at or above the threshold "
                f"{threshold_pct}%. The exemption only releases when "
                "the projected gain is below the threshold. Perform "
                "the rewrite instead."
            )

        # All four conditions hold.
        self.stdout.write(
            "[REWRITE QUOTA EXEMPTION VERIFIED: "
            f"areas={','.join(areas)} "
            f"python_lines={python_lines} "
            f"baseline={baseline_value} "
            f"projected={projected_value} "
            f"gain_pct={recomputed} "
            f"threshold_pct={threshold_pct} "
            "verdict=tiny_gain_or_no_python_remains]"
        )
