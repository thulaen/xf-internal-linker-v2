"""Generate AI-readable benchmark reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.benchmarks.models import BenchmarkRun


def generate_report(run: BenchmarkRun) -> str:
    """Build a plain-text report suitable for pasting into an AI assistant."""
    lines = [
        f"BENCHMARK REPORT -- {run.started_at:%Y-%m-%d %H:%M} UTC",
        "=" * 50,
        "",
    ]

    results = run.results.all().order_by("status", "language", "extension")

    slow = [r for r in results if r.status == "slow"]
    ok = [r for r in results if r.status == "ok"]
    fast = [r for r in results if r.status == "fast"]

    if slow:
        lines.append("SLOW FUNCTIONS (action needed):")
        for i, r in enumerate(slow, 1):
            mean_ms = r.mean_ns / 1_000_000
            threshold_ms = (r.threshold_ns or r.mean_ns) / 1_000_000
            ratio = r.mean_ns / max(r.threshold_ns or 1, 1)
            lines.append(
                f"  {i}. [{r.language.upper()}] {r.extension}.{r.function_name} "
                f"-- {mean_ms:.1f}ms @ {r.input_size} "
                f"(baseline: {threshold_ms:.1f}ms, {ratio:.1f}x slower)"
            )
        lines.append("")

    if ok:
        lines.append("OK FUNCTIONS (monitor):")
        for i, r in enumerate(ok, 1):
            mean_ms = r.mean_ns / 1_000_000
            lines.append(
                f"  {i}. [{r.language.upper()}] {r.extension}.{r.function_name} "
                f"-- {mean_ms:.1f}ms @ {r.input_size}"
            )
        lines.append("")

    lines.append(f"FAST FUNCTIONS ({len(fast)} total): all within baseline")
    lines.append("")

    lines.append(f"Total benchmarked: {len(results)}")
    lines.append(f"Fast: {len(fast)} | OK: {len(ok)} | Slow: {len(slow)}")

    return "\n".join(lines)
