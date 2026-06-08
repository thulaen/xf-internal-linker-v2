from __future__ import annotations

import re
import shlex
from pathlib import Path


DESTRUCTIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("docker volume rm", re.compile(r"\bdocker\s+volume\s+rm\b", re.IGNORECASE)),
    ("docker volume prune", re.compile(r"\bdocker\s+volume\s+prune\b", re.IGNORECASE)),
    ("docker system prune", re.compile(r"\bdocker\s+system\s+prune\b", re.IGNORECASE)),
    ("docker compose down -v", re.compile(r"\bdocker\s+compose\s+down\b.*(?:^|\s)-v(?:\s|$)", re.IGNORECASE)),
    ("docker compose rm", re.compile(r"\bdocker\s+compose\s+rm\b", re.IGNORECASE)),
)


def command_is_allowed(command: str, repo_root: Path | None = None) -> tuple[bool, str | None]:
    """Return whether a Docker command avoids protected data deletion."""
    del repo_root
    normalized = _normalize_command(command)
    if "docker" not in normalized.lower():
        return True, None
    for name, pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(normalized):
            return False, name
    return True, None


def block_message(command: str, pattern: str | None) -> str:
    rule = pattern or "destructive Docker command"
    return (
        f"BLOCKED: {rule}\n"
        "WHY: This command can delete Docker volumes, containers, or cached state that may hold local data.\n"
        "UNBLOCK: Use a non-destructive Docker command, or add the documented exemption marker only for examples.\n"
        f"COMMAND: {command}\n"
    )


def _normalize_command(command: str) -> str:
    try:
        return " ".join(shlex.split(command, posix=False))
    except ValueError:
        return command.strip()
