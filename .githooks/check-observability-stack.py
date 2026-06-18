#!/usr/bin/env python3
"""
Pre-commit hook: verify every observability service is up in Kubernetes.

Hard-blocks every code-changing commit when any service in the named
tier is missing or not Ready.  The list mirrors
the ABSOLUTE rule added 2026-05-22 — see
`docs/specs/fr-observability-always-on-and-no-deferral.md` and
`CLAUDE.md` / `AGENTS.md` / `CODEX.md` / `GEMINI.md`.

States the hook ACCEPTS:
  * At least one pod with `status.phase="Running"` and every container Ready.

States the hook BLOCKS on:
  * No matching pod.
  * Any matching pod that is not Running and Ready.

Run manually:
    python .githooks/check-observability-stack.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
K8S_NAMESPACE = "xf-obs"
KUBECTL_ENV = "XF_OBSERVABILITY_KUBECTL"
K8S_SSH_HOST_ENV = "XF_OBSERVABILITY_K8S_SSH_HOST"
DEFAULT_K8S_SSH_HOST = "mint-wifi"

# 2026-05-23 — Phase K.4 DRY refactor: the observability + quality tier
# list now lives in ``config/observability-services.json`` as a single
# source of truth.  ``backend/apps/observability/management/commands/
# check_observability_health.py`` reads the same JSON so the
# session-start ritual and this pre-commit gate never drift.
# ``glitchtip-init`` is intentionally excluded in the JSON because it
# is an init job that exits after running. See
# docs/specs/fr-observability-always-on-and-no-deferral.md.
_SERVICES_CONFIG = REPO_ROOT / "config" / "observability-services.json"


def _load_observability_services() -> tuple[str, ...]:
    try:
        payload = json.loads(_SERVICES_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()
    services = payload.get("services") or []
    return tuple(str(name) for name in services if isinstance(name, str))


def _mint_observability_host() -> str:
    """Mint's address. One env var is the single source (default = reserved WiFi IP)."""
    return os.environ.get("MINT_OBSERVABILITY_HOST", "192.168.0.91")


def _load_remote_services() -> tuple[dict, ...]:
    """Return remote observability services.

    These run on helper hosts, so they are checked by HTTP or SSH.
    Each entry with a ``health_url`` is verified over the network. A
    ``${MINT_OBSERVABILITY_HOST}`` token in a health_url is expanded from the
    single Mint-address env var so the cluster's address lives in one place.
    """
    try:
        payload = json.loads(_SERVICES_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()
    host = _mint_observability_host()
    resolved: list[dict] = []
    for item in payload.get("remote_services") or []:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        health_url = entry.get("health_url")
        if isinstance(health_url, str):
            entry["health_url"] = health_url.replace("${MINT_OBSERVABILITY_HOST}", host)
        resolved.append(entry)
    return tuple(resolved)


OBSERVABILITY_SERVICES: tuple[str, ...] = _load_observability_services()
REMOTE_SERVICES: tuple[dict, ...] = _load_remote_services()

# Healthcheck states the hook accepts.  An empty Health string is
# accepted because not every observability container declares a
# healthcheck (e.g. otel-collector typically does not).
def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _ps_for_service(service: str) -> dict | None:
    """Return the Kubernetes pod-list JSON for *service*, or None."""
    kubectl = os.environ.get(KUBECTL_ENV, "kubectl")
    try:
        result = subprocess.run(
            [
                *_kubectl_command(kubectl),
                "-n",
                K8S_NAMESPACE,
                "get",
                "pods",
                "-l",
                f"app={service}",
                "-o",
                "json",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    stdout = (result.stdout or "").strip()
    if not stdout:
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _kubectl_command(kubectl: str) -> list[str]:
    if shutil.which(kubectl):
        return [kubectl]
    return ["ssh", os.environ.get(K8S_SSH_HOST_ENV, DEFAULT_K8S_SSH_HOST), kubectl]


def _check_service(service: str) -> str | None:
    """Return an error message string if *service* is not acceptably up,
    or None when the service is in an accepted state.
    """
    record = _ps_for_service(service)
    if record is None:
        return f"  {service}: Kubernetes query failed or returned invalid JSON"
    items = record.get("items") or []
    if not items:
        return f"  {service}: no Kubernetes pod found with label app={service}"
    for pod in items:
        problem = _pod_not_ready_reason(service, pod)
        if problem is not None:
            return problem
    return None


def _pod_not_ready_reason(service: str, pod: dict) -> str | None:
    name = str((pod.get("metadata") or {}).get("name") or service)
    status = pod.get("status") or {}
    phase_problem = _pod_phase_problem(service, name, status)
    if phase_problem is not None:
        return phase_problem
    readiness_problem = _pod_readiness_problem(service, name, status)
    return readiness_problem


def _pod_phase_problem(service: str, name: str, status: dict) -> str | None:
    phase = str(status.get("phase") or "")
    if phase != "Running":
        return f"  {service}: pod {name} phase is {phase!r}, expected 'Running'"
    return None


def _pod_readiness_problem(service: str, name: str, status: dict) -> str | None:
    statuses = status.get("containerStatuses") or []
    if not statuses:
        return f"  {service}: pod {name} has no container readiness status"
    not_ready = [str(item.get("name") or "container") for item in statuses if not item.get("ready")]
    if not_ready:
        return f"  {service}: pod {name} containers not Ready: {', '.join(not_ready)}"
    return None


def _check_remote_service(service: dict) -> str | None:
    """Return an error string if a remote service is not reachable.

    Entries that declare a ``health_command`` are checked by running the
    fixed command list. Entries that declare a ``health_url`` are probed over
    HTTP. Entries without either field are verified by the matching
    host-specific deep checker and are skipped here.
    """
    label = service.get("label") or service.get("container") or "remote service"
    host = service.get("host") or service.get("context") or "remote host"
    health_command = service.get("health_command")
    health_url = service.get("health_url")
    if not health_command and not health_url:
        return None
    # Optional substring the health body must contain (e.g. SonarQube returns
    # JSON with "status":"UP"; Pyroscope's /ready returns plain "ready"). When
    # absent, any successful command or HTTP 200 is treated as healthy.
    expect = service.get("health_ok_contains")
    if health_command:
        return _check_remote_command(label, host, health_command, expect)
    return _check_remote_http(label, host, health_url, expect)


def _check_remote_command(
    label: str,
    host: str,
    health_command: object,
    expect: object,
) -> str | None:
    if not _is_command_list(health_command):
        return f"  {label} (on {host}): health_command must be a string list"
    result = subprocess.run(
        _ssh_docker_command(health_command),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        return f"  {label} (on {host}): health_command failed (exit {result.returncode})"
    return _body_expectation_error(label, host, result.stdout, expect)


def _check_remote_http(
    label: str,
    host: str,
    health_url: object,
    expect: object,
) -> str | None:
    try:
        with urllib.request.urlopen(health_url, timeout=8) as response:  # nosec B310 - fixed config URL
            status_code = getattr(response, "status", 200)
            body = response.read(512).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return (
            f"  {label} (on {host}): could not reach {health_url} "
            f"({exc.__class__.__name__})"
        )
    if status_code != 200:
        return f"  {label} (on {host}): HTTP {status_code} from {health_url}"
    return _body_expectation_error(label, host, body, expect)


def _is_command_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(part, str) for part in value)


def _body_expectation_error(
    label: str,
    host: str,
    body: str,
    expect: object,
) -> str | None:
    if not expect:
        return None
    clean_expect = str(expect).replace(" ", "")
    if clean_expect in body.replace(" ", ""):
        return None
    return f"  {label} (on {host}): health body did not contain {expect!r} ({body[:120]!r})"


def main() -> int:
    failures: list[str] = []
    for service in OBSERVABILITY_SERVICES:
        problem = _check_service(service)
        if problem is not None:
            failures.append(problem)
    for remote in REMOTE_SERVICES:
        problem = _check_remote_service(remote)
        if problem is not None:
            failures.append(problem)
    if not failures:
        return 0
    message = (
        "FAIL check-observability-stack: one or more observability or "
        "quality containers are not running.\n"
        "WHY: the 2026-05-22 ABSOLUTE rule "
        "`Observability + quality stack must always be running` "
        "forbids stopping any of these containers to dodge a hook, "
        "silence an importer, or bypass an honest check.  See "
        "`docs/specs/fr-observability-always-on-and-no-deferral.md`.\n"
        "DOWN:\n"
        + "\n".join(failures)
        + "\nUNBLOCK: inspect the service with "
        "`kubectl -n xf-obs get pods -l app=<service>` and fix the "
        "Kubernetes rollout. For helper-host services, verify the SSH or HTTP "
        "health check named above. Re-run the commit once every service is "
        "reachable.\n"
    )
    return _fail(message)


def _ssh_docker_command(command: list[str]) -> list[str]:
    if len(command) >= 4 and command[:2] == ["docker", "--context"]:
        host = command[2]
        return ["ssh", host, "docker", *command[3:]]
    return command


if __name__ == "__main__":
    sys.exit(main())
