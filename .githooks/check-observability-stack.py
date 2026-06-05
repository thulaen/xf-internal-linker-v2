#!/usr/bin/env python3
"""
Pre-commit hook: verify every observability + quality container is up.

Hard-blocks every code-changing commit when any container in the named
tier is missing, exited, restarting, or unhealthy.  The list mirrors
the ABSOLUTE rule added 2026-05-22 — see
`docs/specs/fr-observability-always-on-and-no-deferral.md` and
`CLAUDE.md` / `AGENTS.md` / `CODEX.md` / `GEMINI.md`.

States the hook ACCEPTS:
  * `State="running"` AND Health is `starting`, `healthy`, or absent.

States the hook BLOCKS on:
  * `State` != `running` (created, paused, exited, dead, removing,
    restarting)
  * `Health` of `unhealthy`
  * Container absent from `docker compose ps --format json` output.

Run manually:
    python .githooks/check-observability-stack.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

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


def _load_remote_services() -> tuple[dict, ...]:
    """Return remote observability services.

    These run on helper hosts, so they are not in the local
    ``docker compose ps`` output.
    Each entry with a ``health_url`` is verified over the network.
    """
    try:
        payload = json.loads(_SERVICES_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()
    remote = payload.get("remote_services") or []
    return tuple(item for item in remote if isinstance(item, dict))


OBSERVABILITY_SERVICES: tuple[str, ...] = _load_observability_services()
REMOTE_SERVICES: tuple[dict, ...] = _load_remote_services()

# Healthcheck states the hook accepts.  An empty Health string is
# accepted because not every observability container declares a
# healthcheck (e.g. otel-collector typically does not).
ACCEPTED_HEALTH = frozenset({"", "healthy", "starting"})

# Container State value the hook accepts.  Anything else is a block.
ACCEPTED_STATE = "running"


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _ps_for_service(service: str) -> dict | None:
    """Return the docker compose ps JSON record for *service*, or None.

    docker compose ps emits one JSON line per matching container; we
    request a single service so the first valid line is the only one.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json", service],
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
    # docker compose emits ND-JSON; the first non-empty line is the
    # service's record.  Older Compose versions can emit a JSON array.
    first_line = stdout.splitlines()[0].strip()
    if not first_line:
        return None
    try:
        parsed = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    # The array form: parsed is a list of one or more records.
    if isinstance(parsed, list):
        return parsed[0] if parsed else None
    return parsed if isinstance(parsed, dict) else None


def _check_service(service: str) -> str | None:
    """Return an error message string if *service* is not acceptably up,
    or None when the service is in an accepted state.
    """
    record = _ps_for_service(service)
    if record is None:
        return (
            f"  {service}: container is absent from `docker compose ps` "
            "(no record found)"
        )
    state = (record.get("State") or "").strip()
    health = (record.get("Health") or "").strip()
    if state != ACCEPTED_STATE:
        return (
            f"  {service}: State={state!r} (expected {ACCEPTED_STATE!r})"
        )
    if health not in ACCEPTED_HEALTH:
        return (
            f"  {service}: Health={health!r} "
            f"(expected one of {sorted(ACCEPTED_HEALTH)})"
        )
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
        if not isinstance(health_command, list) or not all(
            isinstance(part, str) for part in health_command
        ):
            return f"  {label} (on {host}): health_command must be a string list"
        result = subprocess.run(
            health_command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        body = result.stdout
        if result.returncode != 0:
            return (
                f"  {label} (on {host}): health_command failed "
                f"(exit {result.returncode})"
            )
        if expect and expect.replace(" ", "") not in body.replace(" ", ""):
            return (
                f"  {label} (on {host}): health body did not contain "
                f"{expect!r} ({body[:120]!r})"
            )
        return None
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
    if expect and expect.replace(" ", "") not in body.replace(" ", ""):
        return (
            f"  {label} (on {host}): health body did not contain "
            f"{expect!r} ({body[:120]!r})"
        )
    return None


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
        + "\nUNBLOCK: for local services, bring them back up with "
        "`docker compose up -d <service>` (or restart Docker Desktop "
        "if the whole engine is down).  For Dell-hosted Sonar services, "
        "start them with `scripts/start-dell-sonar-tools.ps1` and verify "
        "with `scripts/check-dell-sonar-tools.ps1`.  For Mint-hosted "
        "profiling services, use `scripts/start-mint-quality-tools.ps1` "
        "and `scripts/check-mint-quality-tools.ps1`.  Re-run the commit once "
        "every service is reachable.\n"
    )
    return _fail(message)


if __name__ == "__main__":
    sys.exit(main())
