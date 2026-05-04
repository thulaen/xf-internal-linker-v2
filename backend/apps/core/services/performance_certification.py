"""Phase 4.11 — Full Performance Certification.

Plain-English: aggregates the latest ``BenchmarkRun`` results into a
single pass/fail "Ready to Ship?" verdict the operator sees on the
dashboard. Per-area breakdown shows which extensions are ``slow``
versus ``ok`` versus ``fast``, so the operator knows exactly which
extension to rebuild before shipping a release.

The cert is a **read-only aggregation** — it does NOT trigger a new
benchmark run (that's ``BenchmarkViewSet.trigger`` / Celery beat).
Reading the latest persisted run + computing pass/fail is fast
(~1-2 s) and idempotent, so the operator can call it as often as
they like.

Storage discipline:
    * ONE ``AppSetting`` row keyed ``performance_cert.last_verdict``
      carries the JSON-encoded verdict.
    * One ``performance_cert.last_run_at`` row carries the ISO-8601
      timestamp.
    * Both via ``update_or_create`` so storage stays bounded at 2 rows.

Citations:
    * ``apps.benchmarks.services.runner`` — the underlying benchmark
      execution we aggregate over.
    * ``apps.benchmarks.models.BenchmarkRun`` / ``BenchmarkResult`` —
      already-persisted source data; the cert is a thin pure-Python
      summariser, no new tables.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


# AppSetting keys for the persisted single-row verdict + timestamp.
_KEY_VERDICT = "performance_cert.last_verdict"
_KEY_RUN_AT = "performance_cert.last_run_at"

# Verdict thresholds. The cert PASSes when every required area meets
# the per-area minimum; FAILs as soon as ONE required area fails. The
# WARNING band exists for non-critical regressions (operator sees a
# yellow chip but can still ship).
_REQUIRED_AREAS = ("cpp", "python")

# A single benchmark function is "passing" when its status is fast or ok.
# "slow" results count toward the WARN budget; >= _WARN_BUDGET slow
# entries pushes the area into FAIL.
_PASSING_STATUSES = frozenset({"fast", "ok"})
_WARN_BUDGET = 3


@dataclass(frozen=True, slots=True)
class AreaSummary:
    """Per-area (cpp / python) verdict + counts."""

    area: str
    fast_count: int
    ok_count: int
    slow_count: int
    total: int
    verdict: str  # "pass" | "warn" | "fail"
    note: str


@dataclass(frozen=True, slots=True)
class CertVerdict:
    """Whole-system pass/fail snapshot."""

    run_at_iso: str
    verdict: str  # "pass" | "warn" | "fail" | "unknown"
    label: str  # short operator-facing summary
    benchmark_run_id: int | None
    benchmark_run_started_at_iso: str
    areas: list[AreaSummary] = field(default_factory=list)
    note: str = ""


def run_performance_certification() -> CertVerdict:
    """Compute + persist the cert verdict from the latest BenchmarkRun.

    Returns a ``CertVerdict`` with the per-area breakdown. Never raises;
    on missing data returns ``verdict="unknown"`` so the operator can
    still see the panel.
    """
    run = _read_latest_completed_run()
    if run is None:
        verdict = CertVerdict(
            run_at_iso=timezone.now().isoformat(),
            verdict="unknown",
            label="No completed benchmark run yet — trigger one first.",
            benchmark_run_id=None,
            benchmark_run_started_at_iso="",
            areas=[],
            note=(
                "No BenchmarkRun has completed yet. POST "
                "/api/benchmarks/trigger/ then re-check this endpoint."
            ),
        )
        _persist_verdict(verdict)
        return verdict

    areas = _summarise_per_area(run)
    overall = _aggregate_verdict(areas)
    label = _label_for(overall, areas)
    verdict = CertVerdict(
        run_at_iso=timezone.now().isoformat(),
        verdict=overall,
        label=label,
        benchmark_run_id=run.pk,
        benchmark_run_started_at_iso=(
            run.started_at.isoformat() if run.started_at else ""
        ),
        areas=areas,
        note=_advisory_for(overall, areas),
    )
    _persist_verdict(verdict)
    return verdict


def get_last_certification() -> CertVerdict | None:
    """Read-only: return the persisted verdict or None if none exists."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=_KEY_VERDICT).first()
        if row is None or not row.value:
            return None
        payload = json.loads(row.value)
        areas = [
            AreaSummary(**a) for a in payload.get("areas", [])
        ]
        return CertVerdict(
            run_at_iso=payload.get("run_at_iso", ""),
            verdict=payload.get("verdict", "unknown"),
            label=payload.get("label", ""),
            benchmark_run_id=payload.get("benchmark_run_id"),
            benchmark_run_started_at_iso=payload.get(
                "benchmark_run_started_at_iso", ""
            ),
            areas=areas,
            note=payload.get("note", ""),
        )
    except Exception:  # noqa: BLE001 — bad JSON / DB blip: treat as no verdict yet.
        logger.debug("performance_cert: verdict read failed", exc_info=True)
        return None


# ── Internal helpers ─────────────────────────────────────────────


def _read_latest_completed_run():
    """Return the most recent BenchmarkRun with status='completed', or None."""
    try:
        from apps.benchmarks.models import BenchmarkRun

        return (
            BenchmarkRun.objects.filter(status="completed")
            .order_by("-started_at")
            .first()
        )
    except Exception:  # noqa: BLE001 — model unavailable on cold start; cert returns "unknown".
        logger.debug(
            "performance_cert: BenchmarkRun read failed", exc_info=True
        )
        return None


def _summarise_per_area(run) -> list[AreaSummary]:
    """Bucket run.results by language; build one AreaSummary per area."""
    try:
        from django.db.models import Count

        rows = (
            run.results.values("language", "status")
            .annotate(c=Count("pk"))
            .order_by("language", "status")
        )
    except Exception:  # noqa: BLE001 — defensive: empty list still yields a typed verdict.
        logger.debug(
            "performance_cert: results aggregate failed", exc_info=True
        )
        return []

    # Build {language: {status: count}}
    per_area: dict[str, dict[str, int]] = {}
    for row in rows:
        lang = row["language"]
        per_area.setdefault(lang, {"fast": 0, "ok": 0, "slow": 0})
        status = row["status"]
        if status in per_area[lang]:
            per_area[lang][status] = row["c"]

    summaries: list[AreaSummary] = []
    # Always emit a row for each required area, even if 0 results — so
    # the operator sees "C++: no benchmarks ran" instead of an empty
    # table that hides the problem.
    seen_areas = set(per_area.keys()) | set(_REQUIRED_AREAS)
    for area in sorted(seen_areas):
        counts = per_area.get(area, {"fast": 0, "ok": 0, "slow": 0})
        summaries.append(_build_area_summary(area, counts))
    return summaries


def _build_area_summary(area: str, counts: dict[str, int]) -> AreaSummary:
    """Compute one AreaSummary from a per-language status histogram."""
    fast = counts.get("fast", 0)
    ok = counts.get("ok", 0)
    slow = counts.get("slow", 0)
    total = fast + ok + slow
    verdict, note = _classify_area(area=area, total=total, slow=slow)
    return AreaSummary(
        area=area,
        fast_count=fast,
        ok_count=ok,
        slow_count=slow,
        total=total,
        verdict=verdict,
        note=note,
    )


def _classify_area(*, area: str, total: int, slow: int) -> tuple[str, str]:
    """Return ``(verdict, note)`` for an area given its counts.

    Pure function — no Django imports — so the verdict logic stays
    independently testable from the AreaSummary dataclass shape.
    """
    if total == 0:
        return (
            "fail" if area in _REQUIRED_AREAS else "warn",
            f"No {area} benchmarks ran. Required areas must produce "
            "at least one result.",
        )
    if slow == 0:
        return "pass", f"All {total} {area} benchmarks meet baseline."
    if slow < _WARN_BUDGET:
        return (
            "warn",
            f"{slow} of {total} {area} benchmarks regressed; "
            f"under the {_WARN_BUDGET}-result fail threshold.",
        )
    return (
        "fail",
        f"{slow} of {total} {area} benchmarks regressed; "
        f"at or over the {_WARN_BUDGET}-result fail threshold.",
    )


def _aggregate_verdict(areas: list[AreaSummary]) -> str:
    """Combine per-area verdicts into one whole-system verdict."""
    if not areas:
        return "unknown"
    verdicts = {a.verdict for a in areas}
    if "fail" in verdicts:
        return "fail"
    if "warn" in verdicts:
        return "warn"
    return "pass"


def _label_for(verdict: str, areas: list[AreaSummary]) -> str:
    """One-line operator summary."""
    if verdict == "pass":
        return "Ready to ship — every benchmark meets baseline."
    if verdict == "warn":
        slow_total = sum(a.slow_count for a in areas)
        return (
            f"Yellow — {slow_total} non-critical regression(s); "
            "consider rebuilding before shipping."
        )
    if verdict == "fail":
        slow_total = sum(a.slow_count for a in areas)
        return (
            f"Hold — {slow_total} regression(s) at or over the fail "
            "threshold. Rebuild affected extensions first."
        )
    return "Unknown — no recent benchmark run to certify."


def _advisory_for(verdict: str, areas: list[AreaSummary]) -> str:
    """Plain-English next-step recommendation."""
    if verdict == "pass":
        return "All systems go. Cert badge stays green until the next run."
    if verdict == "fail":
        slow_areas = [a.area for a in areas if a.verdict == "fail"]
        return (
            f"Failing areas: {', '.join(slow_areas)}. "
            "Run `docker compose build backend` then "
            "`POST /api/benchmarks/trigger/` to recertify."
        )
    if verdict == "warn":
        return (
            "Yellow band — operator may ship but should triage the "
            "regressed benchmarks before next release."
        )
    return "Trigger a benchmark run before this cert is meaningful."


def _persist_verdict(verdict: CertVerdict) -> None:
    """Store the verdict + timestamp as two AppSetting rows. Best-effort."""
    try:
        from apps.core.models import AppSetting

        payload = asdict(verdict)
        AppSetting.objects.update_or_create(
            key=_KEY_VERDICT,
            defaults={"value": json.dumps(payload)},
        )
        AppSetting.objects.update_or_create(
            key=_KEY_RUN_AT,
            defaults={"value": verdict.run_at_iso},
        )
    except Exception:  # noqa: BLE001 — persistence is best-effort; next run will retry.
        logger.debug("performance_cert: persist failed", exc_info=True)


# Convenience for tests / CLI debug — never imported by the API path.
def _read_constants() -> dict[str, Any]:
    return {
        "REQUIRED_AREAS": list(_REQUIRED_AREAS),
        "PASSING_STATUSES": sorted(_PASSING_STATUSES),
        "WARN_BUDGET": _WARN_BUDGET,
    }
