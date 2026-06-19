"""Read-only helpers for Accuracy Lab reports."""

from __future__ import annotations

import json
import os
import shutil
# Runs the repo-owned Accuracy Lab script through this Python executable.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any

from django.conf import settings

_DEFAULT_STATUS = "not_run"
_DEFAULT_MESSAGE = "Accuracy Lab has not generated a local report yet."
_REPORT_FILENAME = "latest.json"
_MARKDOWN_FILENAME = "latest.md"
_RUN_LOCK_FILENAME = "run.lock"
_RUN_STATE_FILENAME = "run_state.json"
_RUN_TIMEOUT_SECONDS = 180
_STALE_LOCK_SECONDS = 600

_DEFAULT_CHECKS = (
    "matlab",
    "numeric_precision",
    "ranking_parity",
    "schema_drift",
    "test_gaps",
    "agent_report",
)


def accuracy_audit_dir() -> Path:
    """Return the local folder where the runner writes report files."""

    configured = getattr(settings, "ACCURACY_AUDIT_DIR", None)
    configured = configured or os.environ.get("XF_ACCURACY_AUDIT_DIR")
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR).parent / "audit" / "accuracy"


def latest_json_path() -> Path:
    """Return the JSON report path without creating files or folders."""

    return accuracy_audit_dir() / _REPORT_FILENAME


def latest_markdown_path() -> Path:
    """Return the Markdown report path without creating files or folders."""

    return accuracy_audit_dir() / _MARKDOWN_FILENAME


def run_state_path() -> Path:
    """Return the local run-state path without creating it."""

    return accuracy_audit_dir() / _RUN_STATE_FILENAME


def missing_report_payload() -> dict[str, Any]:
    """Build the stable response used before the runner has produced output."""

    matlab_path = _matlab_path_hint()
    return {
        "generated_at": None,
        "status": _DEFAULT_STATUS,
        "message": _DEFAULT_MESSAGE,
        "summary": _summary_from_findings([], _DEFAULT_STATUS),
        "tools": {
            "matlab": {
                "available": bool(matlab_path),
                "status": "unknown",
                "version": None,
                "java": None,
                "desktop": None,
                "path": matlab_path,
                "message": _DEFAULT_MESSAGE,
                "cleanup_status": "not_checked",
            }
        },
        "checks": _default_checks(),
        "sophisticated_checks": [],
        "findings": [],
    }


def latest_report_payload() -> dict[str, Any]:
    """Read and normalize the latest report JSON, falling back safely."""

    path = latest_json_path()
    if not path.exists():
        return missing_report_payload()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _corrupt_report_payload(path, exc)
    if not isinstance(payload, dict):
        return _corrupt_report_payload(path, ValueError("report root is not an object"))
    return _normalize_payload(payload)


def accuracy_tools_payload() -> dict[str, Any]:
    """Return tool status plus the backend's current MATLAB path hint."""

    payload = latest_report_payload()
    tools = dict(payload.get("tools") or {})
    matlab = dict(tools.get("matlab") or {})
    matlab.setdefault("path", _matlab_path_hint())
    matlab.setdefault("available", bool(matlab.get("path")))
    tools["matlab"] = matlab
    return {"generated_at": payload.get("generated_at"), "tools": tools}


def accuracy_summary_payload() -> dict[str, Any]:
    """Return report-level status and category cards."""

    payload = latest_report_payload()
    return {
        "generated_at": payload.get("generated_at"),
        "status": payload.get("status", _DEFAULT_STATUS),
        "message": payload.get("message", _DEFAULT_MESSAGE),
        "summary": payload.get("summary") or _summary_from_findings([], _DEFAULT_STATUS),
        "checks": payload.get("checks") or _default_checks(),
        "sophisticated_checks": payload.get("sophisticated_checks") or [],
    }


def accuracy_findings_payload() -> dict[str, Any]:
    """Return normalized findings from the latest Accuracy Lab run."""

    payload = latest_report_payload()
    return {
        "generated_at": payload.get("generated_at"),
        "status": payload.get("status", _DEFAULT_STATUS),
        "findings": [_normalize_finding(item) for item in payload.get("findings", [])],
    }


def accuracy_report_markdown() -> str:
    """Return the latest Markdown report, or a stable not-run report."""

    path = latest_markdown_path()
    if not path.exists():
        return "# Accuracy Lab\n\nAccuracy Lab has not generated a local report yet.\n"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"# Accuracy Lab\n\nThe local report could not be read: {exc}\n"


def run_accuracy_audit_now() -> tuple[int, dict[str, Any]]:
    """Run the local audit runner once and return a plain response payload."""

    lock_path = accuracy_audit_dir() / _RUN_LOCK_FILENAME
    if not _claim_run_lock(lock_path):
        return 409, _run_response("running", "Accuracy Lab is already running.")
    try:
        _write_run_state("running", "Accuracy Lab is running.")
        completed = _run_local_runner()
        if completed.returncode != 0:
            payload = _runner_failed_payload(completed)
        else:
            payload = latest_report_payload()
        state = str(payload.get("status") or "warning")
        message = str(payload.get("message") or "Accuracy Lab finished.")
        _write_run_state(state, message)
        return 200, _run_response(state, message, payload)
    except subprocess.TimeoutExpired as exc:
        payload = _timeout_payload(exc)
        _write_run_state("failed", payload["message"])
        return 504, _run_response("failed", payload["message"], payload)
    finally:
        _release_run_lock(lock_path)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    findings = [_normalize_finding(item) for item in payload.get("findings", [])]
    status = str(payload.get("status") or _status_from_findings(findings))
    return {
        "generated_at": payload.get("generated_at"),
        "status": status,
        "message": str(payload.get("message") or "Latest Accuracy Lab report loaded."),
        "summary": payload.get("summary") or _summary_from_findings(findings, status),
        "tools": payload.get("tools") or missing_report_payload()["tools"],
        "checks": payload.get("checks") or _default_checks(),
        "sophisticated_checks": payload.get("sophisticated_checks") or [],
        "findings": findings,
    }


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).parent


def _runner_script_path() -> Path:
    return _repo_root() / "scripts" / "run_accuracy_audit.py"


def _matlab_path_hint() -> str | None:
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


def _run_local_runner() -> subprocess.CompletedProcess[str]:
    script_path = _runner_script_path()
    command = [sys.executable, str(script_path)]
    if not script_path.exists():
        return subprocess.CompletedProcess(
            command,
            127,
            "",
            f"Runner missing: {script_path}",
        )
    matlab_command = os.environ.get("XF_MATLAB_COMMAND")
    if matlab_command:
        command.extend(["--matlab-command", matlab_command])
    # The command uses this Python executable and a repo-owned script path.
    return subprocess.run(  # nosec B603
        command,
        capture_output=True,
        check=False,
        cwd=str(_repo_root()),
        text=True,
        timeout=_RUN_TIMEOUT_SECONDS,
    )


def _claim_run_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if _lock_is_stale(lock_path):
        lock_path.unlink(missing_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(time.time()))
    return True


def _lock_is_stale(lock_path: Path) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    return age > _STALE_LOCK_SECONDS


def _release_run_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)


def _write_run_state(status: str, message: str) -> None:
    path = run_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"status": status, "message": message, "updated_at": time.time()}
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _run_response(
    status: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"status": status, "message": message, "report": payload}


def _runner_failed_payload(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    detail = (completed.stderr or completed.stdout or "The runner failed.").strip()
    finding = _normalize_finding(
        {
            "id": "accuracy-runner-failed",
            "title": "Accuracy Lab runner failed",
            "risk": "high",
            "impact": "The latest accuracy checks could not finish.",
            "evidence": detail,
            "affected": "scripts/run_accuracy_audit.py",
            "suggested_action": "Ask Codex or Claude to inspect the runner output.",
        }
    )
    return {
        "generated_at": None,
        "status": "failed",
        "message": "Accuracy Lab runner failed.",
        "summary": _summary_from_findings([finding], "failed"),
        "tools": missing_report_payload()["tools"],
        "checks": _default_checks(),
        "findings": [finding],
    }


def _timeout_payload(exc: subprocess.TimeoutExpired) -> dict[str, Any]:
    finding = _normalize_finding(
        {
            "id": "accuracy-runner-timeout",
            "title": "Accuracy Lab runner timed out",
            "risk": "high",
            "impact": "The GUI did not receive completed accuracy results.",
            "evidence": f"Timed out after {exc.timeout} seconds.",
            "affected": "Accuracy Lab runner",
            "suggested_action": "Ask Codex or Claude to inspect MATLAB startup time.",
        }
    )
    return {
        "generated_at": None,
        "status": "failed",
        "message": "Accuracy Lab runner timed out.",
        "summary": _summary_from_findings([finding], "failed"),
        "tools": missing_report_payload()["tools"],
        "checks": _default_checks(),
        "findings": [finding],
    }


def _normalize_finding(raw: Any) -> dict[str, str]:
    item = raw if isinstance(raw, dict) else {}
    return {
        "id": str(item.get("id") or "accuracy-finding"),
        "title": str(item.get("title") or "Accuracy Lab finding"),
        "risk": str(item.get("risk") or "info"),
        "impact": str(item.get("impact") or "No impact was supplied."),
        "evidence": str(item.get("evidence") or "No evidence was supplied."),
        "affected": str(item.get("affected") or "Accuracy Lab"),
        "suggested_action": str(
            item.get("suggested_action") or "Review the evidence before changing code."
        ),
    }


def _default_checks() -> list[dict[str, str]]:
    return [
        {
            "id": check_id,
            "name": check_id.replace("_", " ").title(),
            "status": _DEFAULT_STATUS,
            "message": _DEFAULT_MESSAGE,
        }
        for check_id in _DEFAULT_CHECKS
    ]


def _summary_from_findings(findings: list[dict[str, str]], status: str) -> dict[str, Any]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        risk = finding.get("risk", "info")
        counts[risk if risk in counts else "info"] += 1
    return {"total_findings": len(findings), "status": status, "risk_counts": counts}


def _status_from_findings(findings: list[dict[str, str]]) -> str:
    risks = {finding.get("risk", "info") for finding in findings}
    if "critical" in risks or "high" in risks:
        return "failed"
    if "medium" in risks or "low" in risks:
        return "warning"
    return "passed"


def _corrupt_report_payload(path: Path, exc: Exception) -> dict[str, Any]:
    finding = _normalize_finding(
        {
            "id": "accuracy-report-unreadable",
            "title": "Accuracy Lab report cannot be read",
            "risk": "medium",
            "impact": "The Diagnostics page cannot show the latest accuracy results.",
            "evidence": f"{path}: {exc}",
            "affected": "audit/accuracy/latest.json",
            "suggested_action": "Run the local Accuracy Lab runner again.",
        }
    )
    return {
        "generated_at": None,
        "status": "warning",
        "message": "The latest Accuracy Lab JSON report could not be read.",
        "summary": _summary_from_findings([finding], "warning"),
        "tools": missing_report_payload()["tools"],
        "checks": _default_checks(),
        "findings": [finding],
    }
