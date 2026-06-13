"""Diff-scoped performance-regression decision engine (the Otava gate core).

This is the conservative verdict engine the pre-commit gate calls. It is
scoped STRICTLY to the files in the current commit: it maps changed/added
files to the benchmark functions they could affect, compares each impacted
function's latest recorded result against its own historical baseline, and
returns a strict JSON verdict. It NEVER re-evaluates unchanged modules or
the whole benchmark suite.

Decision rules (conservative — prefer blocking over allowing a regression):
  * a measurable regression in an impacted function  -> block
  * an impacted function whose data is ambiguous
    (too few baseline samples / high variance)        -> block
  * no measurable regression in impacted functions     -> pass
  * a changed file with no associated benchmark is out
    of perf scope (nothing to measure)                 -> pass for that file

The metric compared is wall-clock latency (mean_ns) from BenchmarkResult,
which is what the repo's Mandatory-Benchmark rule records for every hot-path
function. Each issue carries the AutoIssue payload fields the operator needs:
affected_file, metric delta, severity, confidence.

Reference: Matteson & James (2014), "A Nonparametric Approach for Multiple
Change Point Analysis of Multivariate Data", JASA 109(505) —
doi:10.1080/01621459.2013.849605 (the change-point method apache-otava uses;
this gate applies its conservative thresholding to the impacted slice).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# Tuning defaults (overridable by the caller / AppSettings).
DEFAULT_REGRESSION_RATIO = 1.10   # >10% slower than baseline = regression
DEFAULT_MIN_BASELINE_SAMPLES = 3  # fewer than this = ambiguous -> block
DEFAULT_BASELINE_RUNS = 10        # how many prior runs form the baseline window


@dataclass
class Issue:
    issue_type: str       # regression | warning | improvement
    severity: str         # low | medium | high | critical
    affected_file: str
    metric: str
    baseline_value: float
    current_value: float
    delta: float          # fractional change vs baseline (0.25 = +25%)
    confidence: float     # 0.0 - 1.0
    explanation: str
    recommendation: str

    def as_dict(self) -> dict:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "affected_file": self.affected_file,
            "metric": self.metric,
            "baseline_value": round(self.baseline_value, 2),
            "current_value": round(self.current_value, 2),
            "delta": round(self.delta, 4),
            "confidence": round(self.confidence, 2),
            "explanation": self.explanation,
            "recommendation": self.recommendation,
        }


@dataclass
class Verdict:
    decision: str                       # pass | block
    files_analyzed: list[str]
    reason_for_scope: str
    issues: list[Issue] = field(default_factory=list)

    def as_dict(self) -> dict:
        regressions = sum(1 for i in self.issues if i.issue_type == "regression")
        return {
            "decision": self.decision,
            "scope": {
                "files_analyzed": self.files_analyzed,
                "reason_for_scope": self.reason_for_scope,
            },
            "issues": [i.as_dict() for i in self.issues],
            "summary": {
                "files_checked": len(self.files_analyzed),
                "regressions_found": regressions,
            },
        }


def _severity_for_delta(delta: float) -> str:
    if delta >= 0.50:
        return "critical"
    if delta >= 0.25:
        return "high"
    if delta >= 0.10:
        return "medium"
    return "low"


def classify(
    current_ns: float,
    baseline_samples: list[float],
    *,
    regression_ratio: float = DEFAULT_REGRESSION_RATIO,
    min_samples: int = DEFAULT_MIN_BASELINE_SAMPLES,
) -> tuple[str, str, float, float, float]:
    """Classify one function's latest result against its baseline window.

    Pure function (no IO) so it unit-tests without a database. Returns
    ``(issue_type, severity, confidence, delta, baseline_value)`` where
    issue_type is one of regression | warning | improvement | ok.
    'warning' means the data is ambiguous and the caller must BLOCK.
    """
    if len(baseline_samples) < min_samples:
        # Too little history to judge — ambiguous, so the gate blocks.
        baseline = statistics.fmean(baseline_samples) if baseline_samples else current_ns
        return "warning", "medium", 0.4, 0.0, baseline
    baseline = statistics.median(baseline_samples)
    if baseline <= 0:
        return "warning", "medium", 0.4, 0.0, float(baseline)
    delta = (current_ns - baseline) / baseline
    stdev = statistics.pstdev(baseline_samples)
    # Confidence scales with sample count and how far the change sits beyond
    # normal run-to-run noise (one stdev). More samples + a jump well past the
    # noise band => we are confident it is real.
    noise_band = (stdev / baseline) if baseline else 0.0
    sample_conf = min(1.0, len(baseline_samples) / 8.0)
    signal_conf = min(1.0, abs(delta) / (noise_band + 0.05))
    confidence = round(min(0.99, 0.4 + 0.6 * (sample_conf * signal_conf)), 2)
    if current_ns > baseline * regression_ratio:
        return "regression", _severity_for_delta(delta), confidence, delta, baseline
    if current_ns < baseline / regression_ratio:
        return "improvement", "low", confidence, delta, baseline
    return "ok", "low", confidence, delta, baseline


def impacted_functions(
    changed_files: list[str], known_pairs: list[tuple[str, str]]
) -> set[tuple[str, str]]:
    """Map changed/added files to the (extension, function_name) pairs they
    could affect. Pure function (caller supplies the known pairs from the DB)
    so it unit-tests without a database.

    A pair is impacted when its extension or function name appears as a path
    component or filename stem of a changed file (case-insensitive). This is
    deliberately broad on the SCOPED file set — better to evaluate one extra
    related benchmark than to miss a regression in a touched kernel.
    """
    tokens: set[str] = set()
    for path in changed_files:
        lowered = path.lower()
        for part in lowered.replace("\\", "/").split("/"):
            tokens.add(part)
            stem = part.rsplit(".", 1)[0]
            tokens.add(stem)
            tokens.add(stem.removeprefix("test_bench_").removeprefix("bench_"))
    hits: set[tuple[str, str]] = set()
    for ext, fn in known_pairs:
        e, f = ext.lower(), fn.lower()
        if e in tokens or f in tokens or any(e and e in t for t in tokens):
            hits.add((ext, fn))
    return hits


def evaluate(
    changed_files: list[str],
    *,
    baseline_runs: int = DEFAULT_BASELINE_RUNS,
    regression_ratio: float = DEFAULT_REGRESSION_RATIO,
    min_samples: int = DEFAULT_MIN_BASELINE_SAMPLES,
) -> Verdict:
    """Produce the strict diff-scoped verdict for the changed file set."""
    from apps.benchmarks.models import BenchmarkResult

    known = list(
        BenchmarkResult.objects.values_list("extension", "function_name").distinct()
    )
    impacted = impacted_functions(changed_files, known)
    if not impacted:
        return Verdict(
            decision="pass",
            files_analyzed=changed_files,
            reason_for_scope="No benchmarked function maps to the changed files; "
            "nothing to measure in the impacted code paths.",
        )

    issues: list[Issue] = []
    block = False
    for ext, fn in sorted(impacted):
        rows = list(
            BenchmarkResult.objects.filter(extension=ext, function_name=fn)
            .order_by("-run__started_at", "input_size")
            .values_list("input_size", "mean_ns", "run_id")[: baseline_runs + 1]
        )
        for size in {r[0] for r in rows}:
            series = [float(m) for s, m, _ in rows if s == size]
            if not series:
                continue
            current, baseline_window = series[0], series[1:]
            kind, severity, conf, delta, base = classify(
                current, baseline_window,
                regression_ratio=regression_ratio, min_samples=min_samples,
            )
            if kind in ("regression", "warning"):
                block = True
                issues.append(_make_issue(ext, fn, size, kind, severity, conf, delta, base, current))
    return Verdict(
        decision="block" if block else "pass",
        files_analyzed=changed_files,
        reason_for_scope=f"Evaluated {len(impacted)} benchmarked function(s) mapped "
        f"from {len(changed_files)} changed file(s).",
        issues=issues,
    )


def _make_issue(ext, fn, size, kind, severity, conf, delta, base, current) -> Issue:
    affected = f"{ext}.{fn}[{size}]"
    if kind == "warning":
        return Issue(
            "warning", severity, affected, "latency_ns", base, current, delta, conf,
            "Too few baseline samples to judge this impacted benchmark with "
            "confidence; blocking conservatively until history accrues.",
            "Run the benchmark suite a few more times to establish a baseline, "
            "then re-commit.",
        )
    return Issue(
        "regression", severity, affected, "latency_ns", base, current, delta, conf,
        f"Latency rose {delta * 100:.0f}% above the baseline median for an impacted "
        f"function (current {current:.0f}ns vs baseline {base:.0f}ns).",
        "Profile the touched code path and restore latency to baseline, or justify "
        "the regression with a [PERFORMANCE EXEMPTION] before committing.",
    )


def file_regression_autoissues(verdict: Verdict, commit_hash: str) -> int:
    """Emit one deduped AutoIssue per regression/warning issue. Returns count.

    Each issue carries the operator payload the user requires: affected_file,
    commit hash, metric delta, severity, and confidence. The fingerprint is
    stable per (affected_file, metric) so repeat detections bump the existing
    row instead of cloning. The external_id carries the commit so distinct
    commits are distinguishable.
    """
    from apps.auto_issues.models import AutoIssue
    from apps.auto_issues.services.dedup import upsert_dedup

    severity_map = {
        "critical": AutoIssue.SEVERITY_CRITICAL,
        "high": AutoIssue.SEVERITY_HIGH,
        "medium": AutoIssue.SEVERITY_MEDIUM,
        "low": AutoIssue.SEVERITY_LOW,
    }
    count = 0
    for issue in verdict.issues:
        fingerprint = f"perf_regression:{issue.affected_file}:{issue.metric}"
        priority = round(min(0.99, max(0.3, issue.confidence * (1.0 + abs(issue.delta)))), 2)
        upsert_dedup(
            canonical=fingerprint,
            source=AutoIssue.SOURCE_AGENT,
            external_id=f"{fingerprint}:{commit_hash[:12]}",
            fingerprint=fingerprint,
            title=(
                f"[perf_regression] {issue.affected_file} {issue.metric} "
                f"{issue.delta * 100:+.0f}% (commit {commit_hash[:10]})"
            )[:512],
            description=(
                f"{issue.explanation}\n\nRecommendation: {issue.recommendation}\n"
                f"baseline={issue.baseline_value} current={issue.current_value} "
                f"delta={issue.delta} confidence={issue.confidence} commit={commit_hash}"
            ),
            affected_files=[issue.affected_file],
            severity=severity_map.get(issue.severity, AutoIssue.SEVERITY_MEDIUM),
            priority_score=priority,
            occurrence_count=1,
        )
        count += 1
    return count


__all__ = ["Issue", "Verdict", "classify", "impacted_functions", "evaluate",
           "file_regression_autoissues", "_severity_for_delta",
           "DEFAULT_REGRESSION_RATIO", "DEFAULT_MIN_BASELINE_SAMPLES",
           "DEFAULT_BASELINE_RUNS"]
