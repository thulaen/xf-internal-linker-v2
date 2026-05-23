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


OBSERVABILITY_SERVICES: tuple[str, ...] = _load_observability_services()

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


def main() -> int:
    failures: list[str] = []
    for service in OBSERVABILITY_SERVICES:
        problem = _check_service(service)
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
        + "\nUNBLOCK: bring the named containers back up with "
        "`docker compose up -d <service>` (or restart Docker Desktop "
        "if the whole engine is down).  Re-run the commit once "
        "`docker compose ps --format json <service>` reports "
        "`State=running` and `Health` is `healthy` or `starting`.\n"
    )
    return _fail(message)


if __name__ == "__main__":
    sys.exit(main())
