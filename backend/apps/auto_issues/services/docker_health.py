from __future__ import annotations

from dataclasses import dataclass
import subprocess  # nosec B404
from typing import Sequence

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


DEFAULT_TIMEOUT_SECONDS = 20
WINDOWS_DOCKER_CONTEXT = "desktop-linux"
MINT_DOCKER_CONTEXT = "mint"


@dataclass(frozen=True)
class DockerProbe:
    name: str
    command: tuple[str, ...]
    expected_hint: str


@dataclass(frozen=True)
class DockerTarget:
    name: str
    host: str
    probes: tuple[DockerProbe, ...]


def default_targets() -> tuple[DockerTarget, ...]:
    return (
        DockerTarget(
            name="windows-docker-desktop",
            host="Windows laptop Docker Desktop",
            probes=_docker_context_probes(WINDOWS_DOCKER_CONTEXT),
        ),
        DockerTarget(
            name="mint-docker",
            host="Mint helper Docker daemon",
            probes=_docker_context_probes(MINT_DOCKER_CONTEXT),
        ),
    )


def check_docker_health(
    *,
    targets: Sequence[DockerTarget] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    file_issues: bool = True,
) -> dict:
    checked_targets = tuple(targets or default_targets())
    results = [_check_target(target, timeout_seconds) for target in checked_targets]
    return file_docker_health_results(results, file_issues=file_issues)


def file_docker_health_results(
    results: Sequence[dict],
    *,
    file_issues: bool = True,
) -> dict:
    normalized = [_normalize_result(result) for result in results]
    filed = []
    if file_issues:
        filed = [
            _file_docker_issue(result)
            for result in normalized
            if result["status"] != "ok"
        ]
    failures = sum(1 for result in normalized if result["status"] != "ok")
    return {
        "status": "ok" if failures == 0 else "issues-filed" if filed else "failed",
        "checked": len(normalized),
        "failures": failures,
        "results": normalized,
        "autoissues": filed,
    }


def _docker_context_probes(context: str) -> tuple[DockerProbe, ...]:
    return (
        DockerProbe(
            name="version",
            command=("docker", "--context", context, "version"),
            expected_hint="Docker client and server version",
        ),
        DockerProbe(
            name="ps",
            command=("docker", "--context", context, "ps"),
            expected_hint="running containers can be listed",
        ),
        DockerProbe(
            name="info",
            command=("docker", "--context", context, "info"),
            expected_hint="Docker daemon info can be read",
        ),
    )


def _check_target(target: DockerTarget, timeout_seconds: int) -> dict:
    probe_results = [_run_probe(probe, timeout_seconds) for probe in target.probes]
    failed = [probe for probe in probe_results if probe["status"] != "ok"]
    if not failed:
        return {
            "target": target.name,
            "host": target.host,
            "status": "ok",
            "probes": probe_results,
        }
    return {
        "target": target.name,
        "host": target.host,
        "status": "failed",
        "error_kind": _classify_error(failed),
        "probes": probe_results,
    }


def _normalize_result(result: dict) -> dict:
    probes = list(result.get("probes") or [])
    failed = [probe for probe in probes if probe.get("status") != "ok"]
    if not failed:
        return {
            **result,
            "status": "ok",
            "error_kind": result.get("error_kind", ""),
        }
    return {
        **result,
        "status": "failed",
        "error_kind": result.get("error_kind") or _classify_error(failed),
    }


def _run_probe(probe: DockerProbe, timeout_seconds: int) -> dict:
    try:
        completed = subprocess.run(  # nosec B603
            list(probe.command),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": probe.name,
            "status": "timeout",
            "command": " ".join(probe.command),
            "expected": probe.expected_hint,
            "output": _trim_text(exc.stdout),
            "error": _trim_text(exc.stderr) or f"timed out after {timeout_seconds}s",
        }
    except OSError as exc:
        return {
            "name": probe.name,
            "status": "error",
            "command": " ".join(probe.command),
            "expected": probe.expected_hint,
            "output": "",
            "error": _trim_text(str(exc)),
        }
    if completed.returncode == 0:
        return {
            "name": probe.name,
            "status": "ok",
            "command": " ".join(probe.command),
            "expected": probe.expected_hint,
        }
    return {
        "name": probe.name,
        "status": "error",
        "command": " ".join(probe.command),
        "expected": probe.expected_hint,
        "output": _trim_text(completed.stdout),
        "error": _trim_text(completed.stderr),
        "returncode": completed.returncode,
    }


def _classify_error(failed: Sequence[dict]) -> str:
    text = "\n".join(
        str(probe.get("error") or probe.get("output") or "")
        for probe in failed
    ).lower()
    if "500 internal server error" in text or "returned 500" in text:
        return "http_500"
    if any(probe["status"] == "timeout" for probe in failed):
        return "timeout"
    if "cannot connect" in text or "daemon is not running" in text:
        return "daemon_unreachable"
    return "docker_error"


def _file_docker_issue(result: dict) -> dict:
    error_kind = result.get("error_kind") or "docker_error"
    canonical = canonical_fingerprint(
        f"docker-health::{result['target']}::{error_kind}",
        "",
    )
    failing = [
        probe for probe in result["probes"]
        if probe["status"] != "ok"
    ]
    title = f"Docker health failed on {result['host']}: {error_kind}"
    description = (
        f"Docker watchdog detected `{error_kind}` on {result['host']}.\n\n"
        f"Failing probes: {', '.join(probe['name'] for probe in failing)}.\n\n"
        "First error:\n"
        f"{(failing[0].get('error') or failing[0].get('output') or 'no output')[:1200]}"
    )
    issue, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"docker-health:{result['target']}:{error_kind}",
        fingerprint=canonical,
        title=title,
        description=description,
        affected_files=[
            "scripts/check-docker-health.ps1",
            "backend/apps/auto_issues/services/docker_health.py",
        ],
        category_key="docker-health",
        severity=_severity_for(error_kind),
        priority_score=0.9 if error_kind == "http_500" else 0.75,
        occurrence_count=1,
    )
    return {"id": issue.id, "outcome": outcome, "target": result["target"]}


def _severity_for(error_kind: str) -> str:
    if error_kind in {"http_500", "daemon_unreachable"}:
        return AutoIssue.SEVERITY_HIGH
    return AutoIssue.SEVERITY_MEDIUM


def _trim_text(value: object, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[-limit:]
