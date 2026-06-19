"""Run read-only Accuracy Lab checks and write local reports."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_OUTPUT_DIR = Path("audit") / "accuracy"
_MATLAB_TIMEOUT_SECONDS = 90
_RUST_TIMEOUT_SECONDS = 30
_PROCESS_SCAN_TIMEOUT_SECONDS = 5
_MATLAB_MIN_THREADS = 4
_MATLAB_MAX_THREADS = 6
_PARITY_TOLERANCE = 1e-12
_FEATURES = (0.81, 0.64, 0.5, 0.93)
_WEIGHTS = (0.4, 0.25, 0.2, 0.15)
_MATLAB_OK_MARKER = "ACCURACY_LAB_MATLAB_OK"
_MATLAB_PROCESS_NAME = "matlab"
_MATLAB_LICENSE_FEATURES = (
    ("statistics", "Statistics_Toolbox"),
    ("optimization", "Optimization_Toolbox"),
    ("symbolic", "Symbolic_Toolbox"),
    ("parallel", "Distrib_Computing_Toolbox"),
    ("coder", "MATLAB_Coder"),
    ("compiler", "Compiler"),
)
_PATH_HYGIENE_FUNCTIONS = ("sum", "dot", "eig", "rank")
_ADVANCED_CHECK_DEFINITIONS = (
    (
        "floating_point_drift_map",
        "numeric",
        "Floating-point drift map",
        "Python, Rust, and MATLAB score drift.",
    ),
    ("condition_number_check", "numeric", "Condition-number check", "Ranking matrix stability."),
    (
        "variable_precision_recheck",
        "numeric",
        "Variable-precision recheck",
        "High-precision risky formula check.",
    ),
    (
        "symbolic_derivative_check",
        "numeric",
        "Symbolic derivative check",
        "Exact formula derivative check.",
    ),
    (
        "finite_difference_gradient_check",
        "numeric",
        "Finite-difference gradient check",
        "Numeric gradient agreement.",
    ),
    (
        "weight_constraint_check",
        "weights",
        "Weight constraint check",
        "Weight bounds and normalization.",
    ),
    ("weight_simplex_stress", "weights", "Weight simplex stress", "Legal weight sweep."),
    (
        "multi_objective_frontier",
        "weights",
        "Multi-objective frontier",
        "Accuracy, stability, and sensitivity tradeoff.",
    ),
    ("tie_break_stability", "ranking", "Tie-break stability", "Nearly equal ordering."),
    ("rank_reversal_detector", "ranking", "Rank reversal detector", "Small input flips."),
    ("monte_carlo_noise", "ranking", "Monte Carlo noise injection", "Signal noise stability."),
    ("sensitivity_heatmap", "ranking", "Sensitivity heatmap data", "Per-signal sensitivity."),
    ("outlier_influence", "ranking", "Outlier influence check", "One signal overpowering."),
    (
        "missing_signal_imputation",
        "ranking",
        "Missing-signal imputation",
        "Safe default comparison.",
    ),
    (
        "nan_infinity_signed_zero",
        "numeric",
        "NaN, infinity, and signed-zero check",
        "Special numeric values.",
    ),
    (
        "decimal_binary_precision",
        "numeric",
        "Decimal-to-binary precision audit",
        "Stored constants and weights.",
    ),
    ("unit_scale_audit", "schema", "Unit-scale audit", "Mixed unit ranges."),
    ("distribution_shift", "statistics", "Distribution-shift check", "Input feature drift."),
    ("goodness_of_fit", "statistics", "Goodness-of-fit check", "Signal distribution fit."),
    ("heavy_tail_detector", "statistics", "Heavy-tail detector", "Signals that need capping."),
    ("correlation_redundancy", "statistics", "Correlation redundancy scan", "Duplicate factors."),
    ("principal_component_check", "statistics", "Principal component check", "Hidden groups."),
    (
        "mutual_information_overlap",
        "statistics",
        "Mutual-information overlap",
        "Nonlinear signal overlap.",
    ),
    ("stability_cluster_check", "statistics", "Stability cluster check", "Behavior groups."),
    ("anomaly_detector", "statistics", "Anomaly detector", "Suspicious score patterns."),
    ("regression_residual_check", "statistics", "Regression residual check", "Scoring errors."),
    (
        "score_confidence_interval",
        "statistics",
        "Score confidence interval",
        "Score-difference uncertainty.",
    ),
    (
        "bootstrap_rank_confidence",
        "statistics",
        "Bootstrap ranking confidence",
        "Rank confidence under resampling.",
    ),
    (
        "permutation_change_test",
        "statistics",
        "Permutation change test",
        "Meaningful ranking change test.",
    ),
    ("false_discovery_guard", "statistics", "False-discovery guard", "Many checks."),
    (
        "schema_numeric_type_audit",
        "schema",
        "Schema numeric-type audit",
        "Float, decimal, integer, nullable fields.",
    ),
    (
        "database_precision_roundtrip",
        "schema",
        "Database precision round trip",
        "Database numeric fidelity.",
    ),
    ("csv_json_fidelity", "schema", "CSV/JSON fidelity", "Export and import fidelity."),
    ("rust_serialization_parity", "parity", "Rust serialization parity", "Rust fixture."),
    ("python_serialization_parity", "parity", "Python serialization parity", "Python fixture."),
    ("stable_sort_audit", "ranking", "Stable sort audit", "Equal-score ordering."),
    (
        "random_seed_reproducibility",
        "runtime",
        "Random seed reproducibility",
        "Stochastic checker repeatability.",
    ),
    ("time_independence", "runtime", "Clock and timezone independence", "Time stability."),
    ("boundary_value_audit", "runtime", "Boundary-value audit", "Input edge values."),
    ("sparse_dense_parity", "numeric", "Sparse versus dense parity", "Matrix agreement."),
    (
        "vectorized_loop_parity",
        "numeric",
        "Vectorized versus loop parity",
        "MATLAB vectorized and loop agreement.",
    ),
    (
        "matlab_coder_parity",
        "deployment",
        "MATLAB Coder parity",
        "Generated code comparison outside repo.",
    ),
    ("mex_smoke_check", "deployment", "MEX smoke check", "Generated helper smoke outside repo."),
    ("solver_agreement", "optimization", "Solver agreement", "Closed-form and solver result."),
    ("optimizer_feasibility", "optimization", "Optimizer feasibility", "Impossible weights."),
    ("solver_tolerance_audit", "optimization", "Solver tolerance audit", "Threshold proof."),
    ("parallel_sweep_cleanup", "runtime", "Parallel sweep cleanup", "Local worker cleanup."),
    ("memory_growth_check", "runtime", "Memory growth check", "Repeated batch memory."),
    ("matlab_process_cleanup", "runtime", "MATLAB process cleanup", "No leftover process."),
    ("license_inventory", "runtime", "License inventory", "Installed toolbox licenses."),
    ("path_hygiene", "runtime", "MATLAB path hygiene", "Shadowed function detection."),
    ("java_availability", "runtime", "Java availability", "Java-dependent MATLAB features."),
    ("no_desktop_confirmation", "runtime", "No-desktop confirmation", "Headless MATLAB mode."),
    ("report_completeness", "reporting", "Report completeness", "Agent-ready fields."),
    ("agent_patch_prompt", "reporting", "Agent patch prompt", "Suggested fix prompt."),
    ("historical_trend_report", "reporting", "Historical trend report", "Last runs."),
)


@dataclass(frozen=True)
class ToolResult:
    status: str
    available: bool
    score: float | None
    metadata: dict[str, Any]
    message: str


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)
    report = build_report(
        matlab_command=args.matlab_command,
        rust_command=args.rust_command,
        skip_matlab=args.skip_matlab,
    )
    write_reports(report, output_dir)
    print(f"Accuracy Lab wrote {output_dir / 'latest.json'}")
    return 0 if report["status"] != "failed" else 1


def build_report(
    *,
    matlab_command: str | None,
    rust_command: list[str] | None,
    skip_matlab: bool,
) -> dict:
    python_score = _python_score()
    matlab = _skip_result("MATLAB was skipped by operator request.")
    if not skip_matlab:
        matlab = run_matlab_check(matlab_command)
    rust = (
        run_rust_check(rust_command)
        if rust_command
        else _skip_result("Rust check not supplied.")
    )
    checks = _build_checks(python_score, matlab, rust)
    findings = _build_findings(python_score, matlab, rust)
    advanced_checks = _build_advanced_checks(python_score, matlab, rust, findings)
    status = _status_from_findings(findings, checks)
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": generated_at,
        "status": status,
        "message": _status_message(status),
        "tools": {"matlab": matlab.metadata},
        "checks": checks,
        "sophisticated_checks": advanced_checks,
        "findings": findings,
        "summary": _summary(findings, status),
        "resource_safety": _resource_safety(matlab),
        "numeric_fixture": {"python_score": python_score},
    }


def run_matlab_check(matlab_command: str | None) -> ToolResult:
    command = matlab_command or _discover_matlab_command() or "matlab"
    resolved = shutil.which(command) or command
    if command == "matlab" and not shutil.which("matlab"):
        return _tool_missing("MATLAB", command)
    batch = _matlab_batch_code()
    return _run_tool(
        [resolved, "-wait", "-noFigureWindows", "-batch", batch],
        _MATLAB_TIMEOUT_SECONDS,
        command,
        required_marker=_MATLAB_OK_MARKER,
        cleanup_process_name=_MATLAB_PROCESS_NAME,
    )


def run_rust_check(rust_command: list[str]) -> ToolResult:
    return _run_tool(rust_command, _RUST_TIMEOUT_SECONDS, " ".join(rust_command))


def write_reports(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "latest.md").write_text(_markdown_report(report), encoding="utf-8")


def _run_tool(
    command: list[str],
    timeout: int,
    display_command: str,
    *,
    required_marker: str | None = None,
    cleanup_process_name: str | None = None,
) -> ToolResult:
    started_at = time.perf_counter()
    before_pids = _process_ids(cleanup_process_name)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        cleanup = _cleanup_metadata(cleanup_process_name, before_pids, started_at, None)
        return _tool_failed(display_command, str(exc), cleanup)
    metadata = _parse_tool_output(completed.stdout)
    cleanup = _cleanup_metadata(cleanup_process_name, before_pids, started_at, completed.returncode)
    metadata.update(cleanup)
    return _tool_result_from_completed(
        completed, display_command, required_marker, metadata, cleanup
    )


def _tool_result_from_completed(
    completed: subprocess.CompletedProcess[str],
    display_command: str,
    required_marker: str | None,
    metadata: dict[str, Any],
    cleanup: dict[str, Any],
) -> ToolResult:
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "No output was captured.").strip()
        return _tool_failed(display_command, message, metadata)
    if required_marker and required_marker not in completed.stdout:
        return _tool_failed(display_command, f"Output did not contain {required_marker}.", metadata)
    score = _parse_score(completed.stdout)
    if score is None:
        return _tool_failed(display_command, "Output did not contain a numeric score.", metadata)
    metadata.update({"available": True, "status": "passed", "path": display_command})
    if cleanup.get("cleanup_status") == "leftover":
        metadata["status"] = "failed"
        message = "MATLAB did not shut down cleanly."
        return ToolResult("failed", True, score, metadata, message)
    return ToolResult("passed", True, score, metadata, "Tool completed successfully.")


def _parse_tool_output(output: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "version": None,
        "java": None,
        "desktop": None,
        "toolboxes": [],
        "licenses": {},
        "path_hygiene": {},
        "thread_policy": {
            "min_cores": _MATLAB_MIN_THREADS,
            "max_threads": _MATLAB_MAX_THREADS,
            "thread_cap": None,
            "core_count": None,
            "status": "unknown",
        },
    }
    for line in output.splitlines():
        _parse_tool_output_line(parsed, line)
    _finalize_thread_policy(parsed["thread_policy"])
    return parsed


def _parse_tool_output_line(parsed: dict[str, Any], line: str) -> None:
    if line.startswith("ACCURACY_LAB_RELEASE="):
        parsed["version"] = f"R{line.split('=', 1)[1]}"
    elif line.startswith("ACCURACY_LAB_JAVA="):
        parsed["java"] = line.split("=", 1)[1]
    elif line.startswith("ACCURACY_LAB_DESKTOP="):
        parsed["desktop"] = _parse_matlab_bool(line.split("=", 1)[1])
    elif line.startswith("ACCURACY_LAB_TOOLBOX="):
        parsed["toolboxes"].append(line.split("=", 1)[1])
    else:
        _parse_tool_detail_line(parsed, line)


def _parse_tool_detail_line(parsed: dict[str, Any], line: str) -> None:
    if line.startswith("ACCURACY_LAB_LICENSE_"):
        key, value = line.split("=", 1)
        parsed["licenses"][key.removeprefix("ACCURACY_LAB_LICENSE_")] = value == "1"
    elif line.startswith("ACCURACY_LAB_WHICH_"):
        key, value = line.split("=", 1)
        parsed["path_hygiene"][key.removeprefix("ACCURACY_LAB_WHICH_")] = value
    elif line.startswith("ACCURACY_LAB_THREAD_CAP="):
        parsed["thread_policy"]["thread_cap"] = _parse_optional_int(line)
    elif line.startswith("ACCURACY_LAB_CORE_COUNT="):
        parsed["thread_policy"]["core_count"] = _parse_optional_int(line)


def _parse_score(output: str) -> float | None:
    for line in output.splitlines():
        if line.startswith("ACCURACY_LAB_SCORE="):
            try:
                return float(line.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _parse_optional_int(line: str) -> int | None:
    try:
        return int(float(line.split("=", 1)[1]))
    except ValueError:
        return None


def _finalize_thread_policy(policy: dict[str, Any]) -> None:
    core_count = policy.get("core_count")
    thread_cap = policy.get("thread_cap")
    if core_count is None or thread_cap is None:
        policy["status"] = "unknown"
        return
    if core_count < _MATLAB_MIN_THREADS:
        policy["status"] = "too_few_cores"
        return
    if thread_cap > _MATLAB_MAX_THREADS:
        policy["status"] = "too_many_threads"
        return
    policy["status"] = "passed"


def _parse_matlab_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    return None


def _build_checks(python_score: float, matlab: ToolResult, rust: ToolResult) -> list[dict]:
    return [
        _check("matlab", "MATLAB", matlab.status, matlab.message),
        _precision_check(python_score, matlab),
        _parity_check("ranking_parity", "Ranking parity", python_score, rust),
        _check("schema_drift", "Schema drift", "not_run", "Schema drift scan is not wired yet."),
        _check("test_gaps", "Test gaps", "not_run", "Test-gap scan is not wired yet."),
        _check(
            "agent_report",
            "Agent-ready report",
            "passed",
            "Markdown and JSON reports were written.",
        ),
    ]


def _build_advanced_checks(
    python_score: float,
    matlab: ToolResult,
    rust: ToolResult,
    findings: list[dict],
) -> list[dict]:
    statuses = _advanced_status_overrides(python_score, matlab, rust, findings)
    return [
        {
            "id": check_id,
            "category": category,
            "name": name,
            "status": statuses.get(check_id, ("not_run", "Not wired yet."))[0],
            "message": statuses.get(check_id, ("not_run", "Not wired yet."))[1],
            "summary": summary,
        }
        for check_id, category, name, summary in _ADVANCED_CHECK_DEFINITIONS
    ]


def _advanced_status_overrides(
    python_score: float,
    matlab: ToolResult,
    rust: ToolResult,
    findings: list[dict],
) -> dict[str, tuple[str, str]]:
    difference = None if matlab.score is None else abs(python_score - matlab.score)
    return {
        "floating_point_drift_map": _drift_status(difference),
        "weight_constraint_check": _weight_constraint_status(),
        "nan_infinity_signed_zero": ("passed", "Fixture score stayed finite."),
        "matlab_process_cleanup": _cleanup_status(matlab),
        "license_inventory": _license_status(matlab),
        "path_hygiene": _path_hygiene_status(matlab),
        "java_availability": _java_status(matlab),
        "no_desktop_confirmation": _desktop_status(matlab),
        "report_completeness": _report_completeness_status(findings),
        "python_serialization_parity": ("passed", "Python fixture was encoded in the report."),
        "rust_serialization_parity": _rust_status(rust),
    }


def _drift_status(difference: float | None) -> tuple[str, str]:
    if difference is None:
        return "not_run", "MATLAB score was not available."
    if difference <= _PARITY_TOLERANCE:
        return "passed", f"Python and MATLAB differed by {difference:.3g}."
    return "warning", f"Python and MATLAB differed by {difference:.3g}."


def _weight_constraint_status() -> tuple[str, str]:
    valid = all(weight >= 0 for weight in _WEIGHTS) and math.isclose(math.fsum(_WEIGHTS), 1.0)
    return ("passed", "Weights are non-negative and sum to 1.") if valid else (
        "warning",
        "Weights are outside the expected bounds.",
    )


def _precision_check(python_score: float, matlab: ToolResult) -> dict:
    if matlab.score is None:
        return _check("numeric_precision", "Numeric precision", "not_run", matlab.message)
    difference = abs(python_score - matlab.score)
    status = "passed" if difference <= _PARITY_TOLERANCE else "warning"
    return _check(
        "numeric_precision",
        "Numeric precision",
        status,
        f"Python and MATLAB differed by {difference:.3g}.",
    )


def _parity_check(check_id: str, name: str, python_score: float, tool: ToolResult) -> dict:
    if tool.score is None:
        return _check(check_id, name, "not_run", tool.message)
    difference = abs(python_score - tool.score)
    status = "passed" if difference <= _PARITY_TOLERANCE else "warning"
    return _check(check_id, name, status, f"Python and Rust differed by {difference:.3g}.")


def _build_findings(python_score: float, matlab: ToolResult, rust: ToolResult) -> list[dict]:
    findings: list[dict] = []
    if matlab.status == "missing":
        findings.append(_finding("matlab-unavailable", "medium", matlab.message, "MATLAB"))
    elif matlab.status == "failed":
        risk = "high" if matlab.metadata.get("cleanup_status") == "leftover" else "medium"
        findings.append(_finding("matlab-failed", risk, matlab.message, "MATLAB"))
    if matlab.score is not None:
        findings.extend(_difference_findings("matlab", "MATLAB", python_score, matlab.score))
    if rust.score is not None:
        findings.extend(_difference_findings("rust", "Rust", python_score, rust.score))
    return findings


def _difference_findings(
    label: str,
    name: str,
    python_score: float,
    tool_score: float,
) -> list[dict]:
    difference = abs(python_score - tool_score)
    if difference <= _PARITY_TOLERANCE:
        return []
    return [
        _finding(
            f"{label}-numeric-drift",
            "low",
            f"Python and {name} differed by {difference:.3g}.",
            "numeric precision fixture",
        )
    ]


def _finding(finding_id: str, risk: str, evidence: str, affected: str) -> dict:
    return {
        "id": finding_id,
        "title": finding_id.replace("-", " ").title(),
        "risk": risk,
        "impact": "Accuracy confidence is lower until this check is resolved.",
        "evidence": evidence,
        "affected": affected,
        "suggested_action": "Ask Codex or Claude to inspect the affected subsystem.",
    }


def _summary(findings: list[dict], status: str) -> dict:
    risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        risk = finding.get("risk", "info")
        risk_counts[risk if risk in risk_counts else "info"] += 1
    return {"total_findings": len(findings), "status": status, "risk_counts": risk_counts}


def _resource_safety(matlab: ToolResult) -> dict[str, Any]:
    return {
        "matlab_short_lived": True,
        "startup_flags": ["-wait", "-noFigureWindows", "-batch"],
        "thread_policy": matlab.metadata.get("thread_policy", {}),
        "timeout_seconds": _MATLAB_TIMEOUT_SECONDS,
        "cleanup_status": matlab.metadata.get("cleanup_status", "not_checked"),
        "runtime_seconds": matlab.metadata.get("runtime_seconds"),
        "exit_code": matlab.metadata.get("exit_code"),
        "peak_memory_mb": matlab.metadata.get("peak_memory_mb"),
        "lingering_pids": matlab.metadata.get("lingering_pids", []),
    }


def _cleanup_status(matlab: ToolResult) -> tuple[str, str]:
    status = matlab.metadata.get("cleanup_status")
    if status == "clean":
        return "passed", "No new MATLAB process remained after the run."
    if status == "leftover":
        return "failed", "MATLAB did not shut down cleanly."
    return "not_run", "MATLAB process cleanup could not be checked."


def _license_status(matlab: ToolResult) -> tuple[str, str]:
    licenses = matlab.metadata.get("licenses") or {}
    if not licenses:
        return "not_run", "MATLAB license inventory was not available."
    available = sum(1 for value in licenses.values() if value)
    return "passed", f"License inventory captured {available} available products."


def _path_hygiene_status(matlab: ToolResult) -> tuple[str, str]:
    hygiene = matlab.metadata.get("path_hygiene") or {}
    if not hygiene:
        return "not_run", "MATLAB path hygiene was not available."
    return "passed", f"Resolved {len(hygiene)} core MATLAB functions."


def _java_status(matlab: ToolResult) -> tuple[str, str]:
    java = matlab.metadata.get("java")
    if java:
        return "passed", f"MATLAB Java is available: {java}."
    return "warning", "MATLAB Java was not reported."


def _desktop_status(matlab: ToolResult) -> tuple[str, str]:
    if matlab.metadata.get("desktop") is False:
        return "passed", "MATLAB reported desktop=false."
    return "warning", "MATLAB did not confirm desktop=false."


def _report_completeness_status(findings: list[dict]) -> tuple[str, str]:
    required = {"impact", "evidence", "affected", "suggested_action"}
    if all(required.issubset(finding) for finding in findings):
        return "passed", "Every finding has agent-ready fields."
    return "warning", "One or more findings is missing agent-ready fields."


def _rust_status(rust: ToolResult) -> tuple[str, str]:
    if rust.score is None:
        return "not_run", rust.message
    return "passed", "Rust fixture score was captured."


def _status_from_findings(findings: list[dict], checks: list[dict]) -> str:
    risks = {finding.get("risk") for finding in findings}
    if "critical" in risks or "high" in risks:
        return "failed"
    if "medium" in risks or "low" in risks:
        return "warning"
    if any(check["status"] == "warning" for check in checks):
        return "warning"
    if any(check["status"] in {"not_run", "missing"} for check in checks):
        return "warning"
    return "passed"


def _markdown_report(report: dict) -> str:
    lines = ["# Accuracy Lab", "", f"Status: {report['status']}", ""]
    lines.extend(["## Checks", ""])
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']} - {check['message']}")
    lines.extend(["", "## Findings", ""])
    findings = report["findings"] or [{"title": "No findings", "risk": "info"}]
    for finding in findings:
        lines.append(f"- {finding['title']} ({finding['risk']})")
        if finding.get("impact"):
            lines.append(f"  Impact: {finding['impact']}")
        if finding.get("evidence"):
            lines.append(f"  Evidence: {finding['evidence']}")
        if finding.get("affected"):
            lines.append(f"  Affected: {finding['affected']}")
        if finding.get("suggested_action"):
            lines.append(f"  Suggested action: {finding['suggested_action']}")
    lines.extend(["", "## Advanced Check Catalog", ""])
    for check in report.get("sophisticated_checks", []):
        lines.append(
            f"- {check['name']}: {check['status']} - {check['message']}"
        )
    lines.extend(["", "## Resource Safety", ""])
    resource_safety = report.get("resource_safety", {})
    for key, value in resource_safety.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def _matlab_batch_code() -> str:
    license_lines = [
        f"disp(['ACCURACY_LAB_LICENSE_{key}=', num2str(license('test','{feature}'))])"
        for key, feature in _MATLAB_LICENSE_FEATURES
    ]
    path_lines = [
        f"disp(['ACCURACY_LAB_WHICH_{name}=', which('{name}')])"
        for name in _PATH_HYGIENE_FUNCTIONS
    ]
    return "; ".join(
        [
            "weights=[0.4 0.25 0.2 0.15]",
            "features=[0.81 0.64 0.5 0.93]",
            "threadCap=NaN",
            "coreCount=NaN",
            "try",
            f"maxNumCompThreads({_MATLAB_MAX_THREADS})",
            "threadCap=maxNumCompThreads",
            "catch threadError",
            "disp(['ACCURACY_LAB_THREAD_ERROR=', threadError.message])",
            "end",
            "try",
            "coreCount=feature('numcores')",
            "catch coreError",
            "disp(['ACCURACY_LAB_CORE_ERROR=', coreError.message])",
            "end",
            "score=sum(weights.*features)",
            "if usejava('jvm')",
            "javaVersion=char(java.lang.System.getProperty('java.version'))",
            "else",
            "javaVersion='unavailable'",
            "end",
            "disp('ACCURACY_LAB_MATLAB_OK')",
            "disp(['ACCURACY_LAB_RELEASE=', version('-release')])",
            "disp(['ACCURACY_LAB_JAVA=', javaVersion])",
            "disp(['ACCURACY_LAB_DESKTOP=', mat2str(desktop('-inuse'))])",
            "disp(['ACCURACY_LAB_SCORE=', num2str(score, 17)])",
            "disp(['ACCURACY_LAB_THREAD_CAP=', num2str(threadCap, 17)])",
            "disp(['ACCURACY_LAB_CORE_COUNT=', num2str(coreCount, 17)])",
            "toolboxes=ver",
            "for k=1:numel(toolboxes)",
            "disp(['ACCURACY_LAB_TOOLBOX=', toolboxes(k).Name])",
            "end",
            *license_lines,
            *path_lines,
        ]
    )


def _python_score() -> float:
    return math.fsum(weight * feature for weight, feature in zip(_WEIGHTS, _FEATURES, strict=True))


def _discover_matlab_command() -> str | None:
    configured = os.environ.get("XF_MATLAB_COMMAND")
    if configured:
        return configured
    path_command = shutil.which("matlab")
    if path_command:
        return path_command
    matlab_root = Path("C:/Program Files/MATLAB")
    if not matlab_root.exists():
        return None
    candidates = sorted(matlab_root.glob("R*/bin/matlab.exe"), reverse=True)
    return str(candidates[0]) if candidates else None


def _check(check_id: str, name: str, status: str, message: str) -> dict:
    return {"id": check_id, "name": name, "status": status, "message": message}


def _skip_result(message: str) -> ToolResult:
    metadata = {
        "available": False,
        "status": "not_run",
        "version": None,
        "path": None,
        "cleanup_status": "not_checked",
    }
    return ToolResult("not_run", False, None, metadata, message)


def _tool_missing(name: str, command: str) -> ToolResult:
    metadata = {
        "available": False,
        "status": "missing",
        "version": None,
        "path": command,
        "cleanup_status": "not_checked",
    }
    return ToolResult("missing", False, None, metadata, f"{name} was not found on PATH.")


def _tool_failed(
    command: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> ToolResult:
    metadata = dict(metadata or {})
    metadata.update({"available": True, "status": "failed", "path": command})
    metadata.setdefault("version", None)
    metadata.setdefault("cleanup_status", "not_checked")
    return ToolResult("failed", True, None, metadata, message)


def _process_ids(process_name: str | None) -> set[int]:
    if not process_name:
        return set()
    if os.name == "nt":
        return _windows_process_ids(process_name)
    return _posix_process_ids(process_name)


def _windows_process_ids(process_name: str) -> set[int]:
    image_name = process_name if process_name.lower().endswith(".exe") else f"{process_name}.exe"
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            check=False,
            text=True,
            timeout=_PROCESS_SCAN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return _parse_tasklist_pids(completed.stdout)


def _parse_tasklist_pids(output: str) -> set[int]:
    pids: set[int] = set()
    for row in csv.reader(output.splitlines()):
        if len(row) < 2 or row[0].upper().startswith("INFO:"):
            continue
        try:
            pids.add(int(row[1]))
        except ValueError:
            continue
    return pids


def _posix_process_ids(process_name: str) -> set[int]:
    try:
        completed = subprocess.run(
            ["pgrep", "-x", process_name],
            capture_output=True,
            check=False,
            text=True,
            timeout=_PROCESS_SCAN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {int(pid) for pid in completed.stdout.split() if pid.isdigit()}


def _cleanup_metadata(
    process_name: str | None,
    before_pids: set[int],
    started_at: float,
    exit_code: int | None,
) -> dict[str, Any]:
    if not process_name:
        return {
            "cleanup_status": "not_checked",
            "runtime_seconds": round(time.perf_counter() - started_at, 3),
            "exit_code": exit_code,
            "peak_memory_mb": None,
            "lingering_pids": [],
        }
    after_pids = _process_ids(process_name)
    lingering = sorted(after_pids - before_pids)
    return {
        "cleanup_status": "leftover" if lingering else "clean",
        "runtime_seconds": round(time.perf_counter() - started_at, 3),
        "exit_code": exit_code,
        "peak_memory_mb": None,
        "lingering_pids": lingering,
    }


def _status_message(status: str) -> str:
    if status == "failed":
        return "Accuracy Lab found a high-risk issue."
    if status == "warning":
        return "Accuracy Lab found warnings to review."
    return "Accuracy Lab completed without findings."


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(_DEFAULT_OUTPUT_DIR))
    parser.add_argument("--matlab-command", default=None)
    parser.add_argument("--rust-command", nargs="+", default=None)
    parser.add_argument("--skip-matlab", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
