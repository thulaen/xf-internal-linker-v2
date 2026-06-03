#!/usr/bin/env python3
"""PreToolUse hook: enforce test-first discipline for production source writes.

Blocks Write/Edit/MultiEdit on production source files (.sh, .py, .ps1)
unless a matching test file exists.  .yml / .yaml / .json / .toml / .md and
all files under test_ / tests/ / _test. paths are always allowed through.

Exit 0 = allow the write.
Exit 2 + stderr = block the write with a plain-English message.

Claude Code passes the full tool-use JSON on stdin; we only need the path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Extensions that are always exempt from the test-first guard.
EXEMPT_SUFFIXES = {
    ".yml", ".yaml", ".json", ".toml", ".md", ".rst",
    ".txt", ".cfg", ".ini", ".lock",
    ".css", ".scss", ".html", ".svg",
    ".proto", ".http",
}

# Filenames (stem only, no extension) that are always exempt.
EXEMPT_FILENAMES = {
    "Dockerfile",   # Docker build configs are not production source
    "Makefile",
    "GNUmakefile",
}

# Path fragments that identify test files (normalised to forward-slash).
TEST_FRAGMENTS = ("test_", "_test.", "/tests/", "/test/")

# Path fragments that are always exempted (generated, third-party, docs).
ALWAYS_ALLOWED_FRAGMENTS = (
    "/node_modules/",
    "/dist/",
    "/build/",
    "/__pycache__/",
    "/_pb2",
    "_pb2_grpc",
    "/api/gen/",
    ".githooks/",
    "docs/",
    ".claude/",
)


def _normalise(path: str) -> str:
    """Convert backslashes to forward-slashes for consistent matching."""
    return path.replace("\\", "/")


def _is_exempt(path: str) -> bool:
    p = Path(path)
    suffix = p.suffix.lower()
    # Dockerfile, Makefile etc. have no extension � check by filename.
    if p.name in EXEMPT_FILENAMES or p.name.startswith("Dockerfile."):
        return True
    if suffix in EXEMPT_SUFFIXES:
        return True
    norm = _normalise(path)
    if any(frag in norm for frag in ALWAYS_ALLOWED_FRAGMENTS):
        return True
    name = p.name
    # Check test_ prefix and _test. suffix in the filename itself.
    if name.startswith("test_") or "_test." in name:
        return True
    # Check if any parent directory is named "tests" or "test".
    if "/tests/" in norm or "/test/" in norm:
        return True
    return False


def _candidate_test_files(path: str) -> list[Path]:
    """Return paths that would satisfy the test-first requirement."""
    p = Path(path)
    stem = p.stem
    parent = p.parent
    candidates = [
        parent / f"test_{stem}.py",
        parent / f"test_{stem}.sh",
        parent / f"test_{stem}.bats",
        parent / f"{stem}.bats",
        parent / "tests" / f"test_{stem}.py",
        REPO_ROOT / "scripts" / "tests" / f"test_{stem}.py",
        REPO_ROOT / "scripts" / f"test_{stem}.py",
    ]
    return candidates


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # No payload — allow through (e.g. dry-run or unrecognised call)
        return 0

    # Extract the file path from the tool input.
    tool_input = payload.get("tool_input", {})
    file_path: str = tool_input.get("file_path", "") or tool_input.get("path", "")

    if not file_path:
        return 0  # Can't determine path — allow through

    if _is_exempt(file_path):
        return 0

    # Make the path relative to REPO_ROOT for nicer messages.
    try:
        rel = Path(file_path).resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = Path(file_path)

    # Check whether any candidate test file exists.
    candidates = _candidate_test_files(str(rel))
    for candidate in candidates:
        if candidate.exists():
            return 0  # Test file found — allow the write

    # No test file found — block and explain.
    try:
        candidates_display = [
            str(c.relative_to(REPO_ROOT)) if c.is_absolute() else str(c)
            for c in candidates[:4]
        ]
    except ValueError:
        candidates_display = [str(c) for c in candidates[:4]]
    candidates_str = "\n    ".join(candidates_display)
    print(
        f"\nFAIL tdd_write_guard: production file blocked — no matching test file found.\n"
        f"WHY: The test-first rule requires a test file to exist before you write or edit\n"
        f"     a production source file (.py, .sh, .ps1).  This prevents skipping TDD.\n"
        f"BLOCKED FILE: {rel}\n"
        f"CREATE ONE OF:\n"
        f"    {candidates_str}\n"
        f"UNBLOCK: Write the test file first (Red phase), then re-run the Write/Edit.\n"
        f"         .yml / .yaml / .json / .md files are always exempt.\n",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
