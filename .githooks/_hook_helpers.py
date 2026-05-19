"""Shared helpers for the .githooks/ pre-commit hook scripts.

Originally extracted 2026-05-16 to keep Rules J/K/L hooks under the
duplicate-block quality-debt threshold. Expanded 2026-05-17 to resolve
paper-trail #585 (test_case #703): six+ hooks each carried their own
copy of `_read_staged_handoff_diff`, `is_production_source`, and
`parse_iso8601`. The Windows cp1252 default locale crashed one hook
silently on em-dashes / arrows in handoff entries; verifier-result
caching had to be retrofitted per-hook; the picks-segment-scoping bug
in check-registry-read regexed against the whole diff instead of the
scoped marker block.

This module is the single source of truth for:
  - Reading the staged AGENT-HANDOFF.md diff with UTF-8 + errors=replace
  - Listing staged file paths
  - Identifying production source files (the predicate that triggers
    TDD / test-case / paper-trail marker requirements)
  - Strict ISO8601 parsing for `red_run_at` / `green_run_at` markers
  - Caching `manage.py verify_*` results per ID so a 100-marker commit
    shells docker once per unique ID, not per marker

Hook authors: prefer these helpers over rolling your own. The shared
discipline (UTF-8 fallback, list-form subprocess args, 10-second
default timeout) lives here once.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone as dt_tz
from pathlib import Path
from typing import Callable

_DEFAULT_TIMEOUT = 10


def run_git(repo_root: Path, args: list[str], timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Run a git subcommand from `repo_root` and return its stdout text.

    Returns an empty string if git is not on PATH or if the command
    times out. Subprocess uses `text=True` + `encoding='utf-8'` +
    `errors='replace'` so Windows cp1252 default locale doesn't corrupt
    em-dashes / arrows in handoff entries.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def staged_paths(repo_root: Path) -> list[str]:
    """Return staged file paths added/modified/deleted (repo-relative)."""
    stdout = run_git(
        repo_root,
        ["diff", "--cached", "--name-only", "--diff-filter=ACMD"],
    )
    return [line.strip() for line in stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 2026-05-17 — paper-trail #585 / test_case #703 expansion.
# ---------------------------------------------------------------------------


def get_staged_files(repo_root: Path) -> list[str]:
    """Alias for staged_paths(); test_case #703 names this helper explicitly."""
    return staged_paths(repo_root)


def get_staged_handoff_diff(repo_root: Path) -> str:
    """Return the ADDED lines of the staged AGENT-HANDOFF.md diff.

    Runs `git diff --cached --unified=0 -- AGENT-HANDOFF.md`, keeps only
    the added-line markers (`+` prefix, not `+++` header), strips the
    leading `+`, and joins with newlines. Decoded UTF-8 with
    errors=replace so Windows cp1252 default locale doesn't crash on
    em-dashes / arrows.

    This matches the contract every hook previously implemented on its
    own — what we care about is the markers being ADDED by this commit,
    not the surrounding context.
    """
    raw = run_git(
        repo_root,
        ["diff", "--cached", "--unified=0", "--", "AGENT-HANDOFF.md"],
    )
    return "\n".join(
        line[1:]
        for line in raw.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def parse_iso8601(value: str) -> datetime | None:
    """Strict parse of an ISO8601 timestamp; supports `Z` suffix.

    Returns None on empty input or parse failure. Naive timestamps are
    treated as UTC so `red_run_at < green_run_at` comparisons stay
    timezone-safe.
    """
    if not value:
        return None
    normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_tz.utc)
    return dt


def cached_verifier(verify_callable: Callable[[int], dict]) -> Callable[[int], dict]:
    """Return a memoized wrapper around a per-ID verifier callable.

    The cache is per-callable so different verifiers (e.g.
    verify_tdd_lesson vs verify_test_case) don't pollute each other.
    Cuts a 100-marker commit's docker-exec count from O(markers) to
    O(unique IDs).
    """
    cache: dict[int, dict] = {}

    def wrapper(entry_id: int) -> dict:
        if entry_id not in cache:
            cache[entry_id] = verify_callable(entry_id)
        return cache[entry_id]

    return wrapper


# ---------------------------------------------------------------------------
# Production-source predicate. Moved from check-tdd-strict.py:159 and
# check-test-case-mandate.py:118 where it was duplicated identically.
# ---------------------------------------------------------------------------

PRODUCTION_PREFIXES: tuple[str, ...] = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "services/",
    "backend/extensions/",
)

TEST_FILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)test[s]?_"),
    re.compile(r"_test\.go$"),
    re.compile(r"\.spec\.ts$"),
    re.compile(r"\.test\.ts$"),
    re.compile(r"(^|/)tests?(/|$)"),
    re.compile(r"(^|/)__tests__/"),
)

GENERATED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"_pb2\.py$"),
    re.compile(r"_pb2_grpc\.py$"),
    re.compile(r"\.pb\.go$"),
    re.compile(r"_grpc\.pb\.go$"),
    re.compile(r"(^|/)api/gen/"),
    re.compile(r"(^|/)_sidecars_pb/"),
    re.compile(r"(^|/)node_modules/"),
    re.compile(r"(^|/)dist/"),
    re.compile(r"(^|/)build/"),
)

NON_PRODUCTION_EXTENSIONS: tuple[str, ...] = (
    ".md", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".txt",
    # 2026-05-17 — shell scripts use BATS / shellcheck, not Python's
    # strict-TDD discipline. check-tdd-cycle.py's _SOURCE_SUFFIXES already
    # exempts them; aligning _hook_helpers so check-tdd-strict and
    # check-test-case-mandate behave the same way.
    ".sh", ".bash", ".ps1", ".bat", ".cmd",
    # Sphinx / docs build extensions that show up in scripts/ + frontend/.
    ".rst",
)

NON_PRODUCTION_NAMES: tuple[str, ...] = (
    "README", "LICENSE", "AGENT-HANDOFF.md", "AGENTS.md",
    "CLAUDE.md", "CODEX.md", "GEMINI.md",
)


def is_production_source(path: str) -> bool:
    """Return True iff `path` is a production source file needing a TDD/test-case marker.

    Production = inside a known production prefix AND not a test file AND
    not a generated stub AND not a docs/config artefact. Mirrors the
    predicate previously duplicated in check-tdd-strict.py and
    check-test-case-mandate.py — those hooks now import this function.
    """
    if not any(path.startswith(p) for p in PRODUCTION_PREFIXES):
        return False
    if path.endswith(NON_PRODUCTION_EXTENSIONS):
        return False
    name = path.rsplit("/", 1)[-1]
    if name in NON_PRODUCTION_NAMES or name.startswith("README"):
        return False
    for pattern in TEST_FILE_PATTERNS:
        if pattern.search(path):
            return False
    for pattern in GENERATED_PATTERNS:
        if pattern.search(path):
            return False
    return True
