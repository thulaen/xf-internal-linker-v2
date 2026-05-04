"""Heartbeat reporter daemon — runs on every helper PC.

Phase 4.9 sub-gap (carryover from prior session). The helper-side
companion to the main PC's existing ``HelperNodeHeartbeatView`` at
``/api/settings/helpers/<id>/heartbeat/``.

Plain-English: this script runs on the second PC. Every 30 seconds it
samples the helper's CPU + RAM + active-Celery-job count and POSTs
the snapshot to the main PC. The main PC's roster + the operator's
``/api/helpers/`` view + the Confidence Meter contributor all see the
helper as "online" because of these heartbeats.

Operator workflow:

    1. On the main PC:
         python manage.py drf_create_token helper-cpu-1
       (creates a Django authtoken for the helper-cpu-1 service user)

    2. Enroll the helper via POST /api/settings/helpers/ with
       ``{name: "helper-cpu-1", token: "<one-time-hash>", role: "worker", ...}``

    3. Copy the helper's .env file with:
         HELPER_NODE_NAME=helper-cpu-1
         HELPER_AUTH_TOKEN=<the-drf-create-token output from step 1>
         MAIN_PC_BASE_URL=http://main-pc.local

    4. Run this script as a background daemon (or via the
       commented-out helper-heartbeat service in docker-compose-helper.yml):
         python -m apps.core.helpers.heartbeat_reporter

The script never raises into the operator's terminal; every error is
logged + retried on the next interval. If the main PC is unreachable
the reporter keeps trying until it comes back.

Environment variables (all required unless marked optional):
    * HELPER_NODE_NAME        — unique name of this helper, must
                                match a HelperNode row on the main PC
    * HELPER_AUTH_TOKEN       — DRF authtoken hex (from drf_create_token)
    * MAIN_PC_BASE_URL        — http://<main-pc-host>[:port]
    * HEARTBEAT_INTERVAL_SECS — optional, default 30
    * HELPER_REPORTER_LOG_LEVEL — optional, default INFO
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import time
from typing import Any

logger = logging.getLogger("apps.core.helpers.heartbeat_reporter")


DEFAULT_INTERVAL_SECS = 30
DEFAULT_TIMEOUT_SECS = 15
# When the main PC is unreachable we back off so we don't spam its log.
# Capped at 5 minutes — long enough to stop spamming, short enough that
# recovery doesn't take forever.
_BACKOFF_SCHEDULE = (30, 60, 120, 300)


def _read_env() -> dict[str, str | int]:
    """Return validated env config. Exits the process on missing required vars."""
    required = {
        "HELPER_NODE_NAME": os.environ.get("HELPER_NODE_NAME", "").strip(),
        "HELPER_AUTH_TOKEN": os.environ.get("HELPER_AUTH_TOKEN", "").strip(),
        "MAIN_PC_BASE_URL": os.environ.get("MAIN_PC_BASE_URL", "").strip().rstrip("/"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error("heartbeat_reporter: missing env vars: %s", ", ".join(missing))
        sys.exit(2)

    interval = DEFAULT_INTERVAL_SECS
    raw_interval = os.environ.get("HEARTBEAT_INTERVAL_SECS")
    if raw_interval:
        try:
            interval = int(raw_interval)
        except ValueError:
            # Bad operator-supplied env var. Fall back to default but
            # log a warning so the operator sees the typo via container
            # stdout — `pass`-with-no-log made this previously invisible.
            logger.warning(
                "heartbeat_reporter: HEARTBEAT_INTERVAL_SECS=%r is not an integer; "
                "falling back to default %ds",
                raw_interval,
                DEFAULT_INTERVAL_SECS,
            )
    return {**required, "interval": max(5, interval)}


def _sample_local_state() -> dict[str, Any]:
    """Sample CPU% / RAM% / Celery active+queued jobs on this machine."""
    state: dict[str, Any] = {
        "status": "online",
        "active_jobs": 0,
        "queued_jobs": 0,
        "cpu_pct": 0.0,
        "ram_pct": 0.0,
    }
    try:
        import psutil

        state["cpu_pct"] = float(psutil.cpu_percent(interval=0.5))
        vm = psutil.virtual_memory()
        state["ram_pct"] = round(float(vm.percent), 2)
    except Exception:  # noqa: forbidden-pattern silent-except — psutil is optional; missing it just leaves the defaults at 0.0.
        pass

    # Try to count Celery active + queued jobs via the local broker
    # inspect API. Best-effort; helpers without a Celery worker just
    # report active=0 and the main PC's roster reflects that.
    try:
        from celery import current_app

        inspector = current_app.control.inspect(timeout=2)
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        state["active_jobs"] = sum(len(jobs or []) for jobs in active.values())
        state["queued_jobs"] = sum(len(jobs or []) for jobs in reserved.values())
    except Exception:  # noqa: forbidden-pattern silent-except — Celery inspect can fail on a cold helper; defaults to 0 jobs.
        pass

    # Capabilities snapshot — helps the main PC pick this helper for
    # appropriately-sized work. Single-pass; static info.
    try:
        import psutil

        state["capabilities"] = {
            "cpu_cores": psutil.cpu_count(logical=True) or 0,
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            # Helpers don't have a GPU per the Phase 4.9 hard rule;
            # publish 0 so the main PC's router won't accidentally
            # route gpu_required tasks here.
            "gpu_vram_gb": 0,
            "network_quality": "good",
            "hostname": socket.gethostname(),
        }
    except Exception:  # noqa: forbidden-pattern silent-except — capability sample is informational only.
        pass

    return state


def _resolve_node_id(env: dict[str, str | int]) -> int | None:
    """One-time lookup: find this helper's HelperNode id on the main PC.

    Returns the int id on success, or None when the helper isn't yet
    enrolled (operator hasn't run the POST /api/settings/helpers/ step).
    """
    import requests

    base = str(env["MAIN_PC_BASE_URL"])
    name = str(env["HELPER_NODE_NAME"])
    token = str(env["HELPER_AUTH_TOKEN"])
    url = f"{base}/api/settings/helpers/"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {token}"},
            timeout=DEFAULT_TIMEOUT_SECS,
        )
    except requests.RequestException as exc:
        logger.warning("heartbeat_reporter: lookup request failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning(
            "heartbeat_reporter: lookup returned %s %s", resp.status_code, resp.text[:200]
        )
        return None
    try:
        rows = resp.json()
    except ValueError:
        logger.warning("heartbeat_reporter: lookup payload was not JSON")
        return None
    for row in rows or []:
        if row.get("name") == name:
            # Bug fix 2026-05-04: bare int(row.get("id")) crashed with
            # TypeError if the main-PC payload missed the id field or
            # returned a non-numeric value. Defensive coercion + log.
            raw_id = row.get("id")
            try:
                return int(raw_id)
            except (TypeError, ValueError):
                logger.warning(
                    "heartbeat_reporter: helper '%s' lookup returned "
                    "non-integer id %r — treating as not-registered",
                    name,
                    raw_id,
                )
                return None
    logger.warning(
        "heartbeat_reporter: this helper '%s' is not registered on the main PC; "
        "run POST /api/settings/helpers/ to enroll it",
        name,
    )
    return None


def _post_heartbeat(node_id: int, state: dict[str, Any], env: dict[str, str | int]) -> bool:
    """POST one heartbeat. Returns True on 2xx, False on transport / status error."""
    import requests

    base = str(env["MAIN_PC_BASE_URL"])
    token = str(env["HELPER_AUTH_TOKEN"])
    url = f"{base}/api/settings/helpers/{node_id}/heartbeat/"
    try:
        resp = requests.post(
            url,
            json=state,
            headers={"Authorization": f"Token {token}"},
            timeout=DEFAULT_TIMEOUT_SECS,
        )
    except requests.RequestException as exc:
        logger.warning("heartbeat_reporter: heartbeat POST failed: %s", exc)
        return False
    if 200 <= resp.status_code < 300:
        return True
    logger.warning(
        "heartbeat_reporter: heartbeat returned %s %s",
        resp.status_code,
        resp.text[:200],
    )
    return False


def _sleep_with_backoff(consecutive_failures: int, normal_interval: int) -> None:
    """Sleep for ``normal_interval`` on success; back off on consecutive failures.

    Backoff progresses through ``_BACKOFF_SCHEDULE`` so a long main-PC outage
    doesn't generate hundreds of failed POSTs per hour.
    """
    if consecutive_failures == 0:
        time.sleep(normal_interval)
        return
    idx = min(consecutive_failures - 1, len(_BACKOFF_SCHEDULE) - 1)
    sleep_secs = _BACKOFF_SCHEDULE[idx]
    logger.info(
        "heartbeat_reporter: %d consecutive failures; backing off %d s",
        consecutive_failures,
        sleep_secs,
    )
    time.sleep(sleep_secs)


def main() -> int:
    log_level = os.environ.get("HELPER_REPORTER_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    env = _read_env()

    logger.info(
        "heartbeat_reporter: starting; node=%s main=%s interval=%ss",
        env["HELPER_NODE_NAME"],
        env["MAIN_PC_BASE_URL"],
        env["interval"],
    )

    node_id: int | None = None
    consecutive_failures = 0

    try:
        while True:  # noqa: forbidden-pattern unbounded-loop — daemon loop; SIGINT / KeyboardInterrupt is the exit condition (handled by the surrounding except).
            if node_id is None:
                node_id = _resolve_node_id(env)
                if node_id is None:
                    consecutive_failures += 1
                    _sleep_with_backoff(consecutive_failures, int(env["interval"]))
                    continue
                logger.info(
                    "heartbeat_reporter: resolved HelperNode id=%d for name=%s",
                    node_id,
                    env["HELPER_NODE_NAME"],
                )

            snapshot = _sample_local_state()
            ok = _post_heartbeat(node_id, snapshot, env)
            if ok:
                consecutive_failures = 0
                logger.debug(
                    "heartbeat_reporter: posted cpu=%.1f%% ram=%.1f%% active=%d",
                    snapshot.get("cpu_pct", 0.0),
                    snapshot.get("ram_pct", 0.0),
                    snapshot.get("active_jobs", 0),
                )
            else:
                consecutive_failures += 1
                # If the main PC tells us the node is gone, force a re-resolve.
                if consecutive_failures % 5 == 0:
                    logger.info("heartbeat_reporter: forcing node_id re-resolve")
                    node_id = None

            _sleep_with_backoff(consecutive_failures, int(env["interval"]))
    except KeyboardInterrupt:
        logger.info("heartbeat_reporter: SIGINT — exiting cleanly")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
