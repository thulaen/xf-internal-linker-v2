#!/usr/bin/env python3
"""Safe Docker prune + observability-pipeline freshness check.

Two jobs, in order:

  1. SAFE PRUNE — `docker system prune -f` removes stopped containers,
     dangling images, unused networks, and build cache. It NEVER touches
     named volumes (no `-v`), so pgdata / sidecars_data / etc. are safe. This
     reclaims the disk the Docker VHDX silently accumulates on Windows.

  2. PIPELINE FRESHNESS — confirms the observability stack is actually
     *sending problems to AutoIssues*. For each observability source it checks
     whether any AutoIssue was seen in the last 24h. A silent source (running
     container, but no findings) is a WARNING, not a block — a quiet system is
     not necessarily a broken one. The commit is blocked only when the check
     itself cannot run (backend unreachable), because then we cannot prove the
     pipeline works at all.

Whether each container is *running* is enforced separately and earlier by
check-observability-stack.py; this gate does not duplicate that.

Exit codes:
    0 — prune ran (or was skipped) and the pipeline freshness check ran.
    1 — the pipeline freshness check could not run (backend unreachable).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-observability-pipeline: cannot verify the pipeline.\n"
        "WHY: the observability stack must not only run, it must feed problems "
        "into AutoIssues. This check could not confirm that the pipeline is "
        "reachable, so we cannot prove findings are being recorded.\n"
        "UNBLOCK: 1. Inspect why the pipeline or backend is down.\n"
        "         2. Query AutoIssue.lessons_learned from the database for past fixes to this specific problem.\n"
        "         3. Fix the underlying issue using TDD and unit tests so it doesn't happen again.\n"
        "         4. Record your fix and root-cause in a new lessons_learned entry.\n"
        "         5. Ensure the backend container is up (docker compose up -d backend) and re-run.\n"
        f"\nDetail:\n{detail}\n"
    )
    return 1


def _safe_prune() -> str:
    """Run `docker system prune -f` (no volumes). Best-effort; never blocks."""
    try:
        proc = subprocess.run(
            ["docker", "system", "prune", "-f"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "prune skipped (docker unavailable)"
    lines = (proc.stdout or "").strip().splitlines()
    return lines[-1] if lines else "prune ran (nothing to reclaim)"


def _check_pipeline() -> tuple[bool, str]:
    """Run the freshness command in warn mode. Returns (ran_ok, output)."""
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_observability_pipeline", "--hours", "24",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=120,
        )
    except FileNotFoundError:
        return False, "Docker is not available."
    except subprocess.TimeoutExpired:
        return False, "Pipeline check timed out."
    if proc.returncode != 0:
        return False, (proc.stdout + proc.stderr).strip()
    return True, proc.stdout.strip()


def main() -> int:
    prune_summary = _safe_prune()
    sys.stdout.write(f"[DOCKER PRUNE: {prune_summary}]\n")

    ran_ok, output = _check_pipeline()
    if not ran_ok:
        return _fail(output or "(no output)")
    sys.stdout.write(output + "\n")
    # Silence is surfaced by the command as a WARNING line; we do not block.
    if "silent=" in output and "silent=0/" not in output:
        sys.stdout.write(
            "WARN check-observability-pipeline: one or more sources were silent "
            "for 24h — verify their pickers are running if this is unexpected.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
