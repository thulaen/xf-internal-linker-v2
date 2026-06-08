#!/usr/bin/env python3
"""Always-on, drought-aware "fix N" quota gate for configured AutoIssue sources.

Unlike the session-type-scaled quota in check-autoissue-quota, this gate is
ALWAYS on (every commit) and per-source:
a commit is blocked while >= threshold findings of that source are open, unless
>= threshold were resolved this session. A clean source (0 open) never blocks.

Sources are configured in ALWAYS_ON_SOURCES. The actual count + rule live in
`manage.py verify_always_on_quota`; this hook computes the resolved-after
cutoff and shells out per source. Docker-down is a hard FAIL (no skip), like
the other quota gates.

Run manually:
    python .githooks/check-always-on-quota.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "AGENT-HANDOFF.md"

# (source slug, threshold).
ALWAYS_ON_SOURCES: list[tuple[str, int]] = [
    ("prometheus", 10),
    ("compiler", 10),
]

_HEADING_RE = re.compile(r"^#\s+(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b")


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _previous_handoff_stamp() -> str | None:
    """Second '# YYYY-MM-DD HH:MM' heading in AGENT-HANDOFF.md (the prior entry)."""
    try:
        text = HANDOFF.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    stamps = [m.group("stamp") for line in text.splitlines() if (m := _HEADING_RE.match(line))]
    return stamps[1] if len(stamps) >= 2 else None


def _cutoff_stamp() -> str | None:
    """Most recent commit BEFORE the previous handoff, as 'YYYY-MM-DD HH:MM'."""
    prev = _previous_handoff_stamp()
    if not prev:
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", f"--before={prev}", "--format=%cd",
             "--date=format:%Y-%m-%d %H:%M"],
            cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10, check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or "").strip() or None


def _verify_cmd(source: str, threshold: int, cutoff: str | None) -> list[str]:
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_always_on_quota",
        "--source", source, "--threshold", str(threshold),
    ]
    if cutoff:
        cmd.extend(["--resolved-after", cutoff])
    return cmd


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except FileNotFoundError:
        return 2, "Docker is not available."
    except OSError as exc:
        return 2, f"System error: {exc}"
    return result.returncode, (result.stdout + result.stderr).strip()


def _fail(message: str) -> int:
    sys.stderr.write(f"\n\033[31m[check-always-on-quota]\033[0m {message}\n")
    return 1


def main() -> int:
    if not _staged_files():
        return 0
    cutoff = _cutoff_stamp()
    for source, threshold in ALWAYS_ON_SOURCES:
        code, output = _run(_verify_cmd(source, threshold, cutoff))
        if code != 0:
            return _fail(
                f"FAIL: the always-on quota for '{source}' did not pass.\n"
                "WHY: a commit is blocked while the source's open backlog is at "
                f"or above {threshold} and fewer than {threshold} were resolved "
                "this session.\n"
                f"UNBLOCK: {output}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
