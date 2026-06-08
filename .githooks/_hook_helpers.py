"""Shared helpers for the .githooks/ pre-commit hook scripts.

Originally extracted 2026-05-16 to keep Rules J/K/L hooks under the
duplicate-block quality-debt threshold. Expanded 2026-05-17 to resolve
paper-trail #585 (test_case #703): six+ hooks each carried their own
copy of `_read_staged_handoff_diff`, `is_production_source`, and
`parse_iso8601`. The Windows cp1252 default locale crashed one hook
silently on em-dashes / arrows in handoff entries; verifier-result
caching had to be retrofitted per-hook; the picks-segment-scoping bug
in the now-removed check-registry-read gate regexed against the whole diff instead of the
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

import os
import json
import re
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path
from typing import Callable

_DEFAULT_TIMEOUT = 10
_FINDING_SEVERITIES = {"low", "medium", "high", "critical"}
_SUBJECT_RE = re.compile(r"^.+:\d+$")
_HELPER_CRASH_LIMIT = 5
_HELPER_CRASH_WINDOW = timedelta(minutes=60)
LAST_HELPER_WARNING = ""

_BATCH_FLAG_BY_GROUP = {
    "tdd_lessons": "--tdd-lessons",
    "test_cases": "--test-cases",
    "code_review_lessons": "--code-review-lessons",
    "autoissue_quota": "--autoissue-quota",
    "paper_trail_quota": "--paper-trail-quota",
    "paper_trail_evidence": "--paper-trail-evidence",
}


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


# 2026-05-23 — Phase K.3 DRY refactor: the seven code-bearing path
# prefixes were duplicated literally in the now-removed check-sticky-1-read.py
# and check-rewrite-quota.py. The Sticky #1 system, the Rewrite Quota rule,
# the Native Inspection Window, and the Settled-Spec Window all need
# the same predicate ("is this a code-changing commit?"). Promoting
# CODE_PREFIXES + staged_code_files() to the shared module collapses
# four duplicates into one and prevents future drift when a new code
# location enters the modular monolith.
CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
    "services/",
    "docs/specs/",
    "docs/adr/",
)


def staged_code_files(
    repo_root: Path,
    *,
    prefixes: tuple[str, ...] = CODE_PREFIXES,
) -> list[str]:
    """Return staged Added/Copied/Modified/Renamed paths under ``prefixes``.

    The diff-filter intentionally drops Deleted files because they cannot
    carry markers, fail tests, or have their pylint output checked. Hooks
    that need every shape (Deleted included) should call ``staged_paths``
    directly.
    """
    stdout = run_git(
        repo_root,
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
    )
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return [path for path in lines if any(path.startswith(p) for p in prefixes)]


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


def shell_batch_verify(
    categories: dict[str, list[int]],
    *,
    resolved_after: str | None = None,
    timeout: int = 60,
) -> dict:
    """Run manage.py verify_chain_batch once and return its JSON payload."""
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_chain_batch", "--json",
    ]
    for group, ids in categories.items():
        clean_ids = [str(entry_id) for entry_id in ids]
        if not clean_ids:
            continue
        cmd.extend([_BATCH_FLAG_BY_GROUP[group], ",".join(clean_ids)])
    if resolved_after:
        cmd.extend(["--resolved-after", resolved_after])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return _batch_command_failure(str(exc))
    if result.returncode != 0:
        return _batch_command_failure((result.stdout + result.stderr).strip())
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return _batch_command_failure(f"invalid JSON from verify_chain_batch: {exc}")


def _batch_command_failure(reason: str) -> dict:
    return {"__command__": {"status": "fail", "reason": reason or "unknown failure"}}


class HelperEscalatedHard(RuntimeError):
    """Raised when helper crash rate makes soft filing unsafe."""


class CIHardBlock(RuntimeError):
    """Raised when CI must keep the original hard-block behavior."""


def file_finding_or_hard(
    *,
    category: str,
    severity: str,
    subject: str,
    message: str,
    hook: str,
    repo_root: Path | None = None,
    reliability_required: bool = False,
    finding_timeout: int = 10,
    health_timeout: int = 60,
) -> int:
    """File a local hook finding, while preserving CI hard-stop behavior."""
    root = repo_root or Path(__file__).resolve().parents[1]
    if reliability_required and os.environ.get("XF_QUALITY_ENV") != "ci":
        healthy, problem = _run_reliability_health(root, timeout=health_timeout)
        if not healthy:
            sys.stderr.write(
                f"FAIL {hook}: cannot file a soft finding because the "
                f"{problem} health check failed.\n"
                "UNBLOCK: fix the named verification subsystem first, then "
                "rerun the hook so local findings can be recorded safely.\n"
            )
            return 2
    try:
        autoissue_id = file_finding_as_autoissue(
            category=category,
            severity=severity,
            subject=subject,
            message=message,
            repo_root=root,
            hook=hook,
            timeout=finding_timeout,
        )
    except CIHardBlock:
        sys.stderr.write(message)
        if not message.endswith("\n"):
            sys.stderr.write("\n")
        return 2
    except HelperEscalatedHard as exc:
        sys.stderr.write(f"FAIL {hook}: {exc}\n")
        return 2
    if autoissue_id is None:
        print(f"[FINDING FILED: hook={hook} autoissue=#buffered severity={severity}]")
    else:
        print(f"[FINDING FILED: hook={hook} autoissue=#{autoissue_id} severity={severity}]")
    return 0


def _run_reliability_health(repo_root: Path, *, timeout: int = 60) -> tuple[bool, str]:
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_chain_batch", "--health", "--json",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return False, f"verify_chain_batch command: {exc}"
    if result.returncode == 0:
        return True, ""
    detail = _health_failure_detail(result.stdout, result.stderr)
    return False, detail


def _health_failure_detail(stdout: str, stderr: str) -> str:
    payload = _parse_last_json_object(stdout)
    if isinstance(payload, dict):
        broken = [
            f"{key}={value}"
            for key, value in payload.items()
            if value != "ok" and value != 0
        ]
        if broken:
            return ", ".join(broken[:3])
    combined = (stderr or stdout or "unknown subsystem").strip()
    return combined[:240]


def _parse_last_json_object(text: str) -> dict | None:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


def file_finding_as_autoissue(
    *,
    category: str,
    severity: str,
    subject: str,
    message: str,
    repo_root: Path | None = None,
    hook: str = "check-hook",
    agent: str = "codex",
    timeout: int = 10,
) -> int | None:
    """File one hook finding as an AutoIssue, or buffer it when Docker is down."""
    root = repo_root or Path(__file__).resolve().parents[1]
    _validate_finding_inputs(category, severity, subject, message)
    _raise_if_hard_blocked(root)
    payload = _finding_payload(category, severity, subject, message)
    try:
        completed = _run_file_hook_finding_command(payload, root, agent, timeout)
        if completed.returncode != 0:
            _handle_backend_command_failure(root, hook, payload, completed)
            _buffer_finding(payload, repo_root=root, agent=agent)
            return None
        return _parse_autoissue_id(completed.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        _buffer_finding(payload, repo_root=root, agent=agent)
        return None
    except Exception as exc:  # noqa: BLE001 - hook failures must be visible and soft.
        _handle_helper_crash(root, hook, payload, exc)
        return None


def _raise_if_hard_blocked(repo_root: Path) -> None:
    if os.environ.get("XF_QUALITY_ENV") == "ci":
        raise CIHardBlock("CI uses hard-block behavior for hook findings.")
    crash_count = _recent_crash_count(repo_root=repo_root)
    if crash_count <= _HELPER_CRASH_LIMIT:
        return
    latest = _latest_crash_summary(repo_root=repo_root)
    raise HelperEscalatedHard(
        f"helper has crashed {crash_count} times in last 60 min. "
        f"Most recent: {latest}"
    )


def _finding_payload(category: str, severity: str, subject: str, message: str) -> dict:
    return {
        "category": category,
        "severity": severity,
        "subject": subject,
        "message": message,
    }


def _run_file_hook_finding_command(
    payload: dict,
    repo_root: Path,
    agent: str,
    timeout: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker", "compose", "exec", "-T", "backend",
            "python", "manage.py", "file_hook_finding",
            "--category", payload["category"],
            "--severity", payload["severity"],
            "--subject", payload["subject"],
            "--message", payload["message"],
            "--agent", agent,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _handle_helper_crash(repo_root: Path, hook: str, payload: dict, exc: Exception) -> None:
    _log_helper_failure(
        repo_root=repo_root,
        hook=hook,
        category=payload["category"],
        subject=payload["subject"],
        message=payload["message"],
        exc=exc,
    )
    warning = _format_helper_warning(
        hook,
        payload["subject"],
        _recent_crash_count(repo_root=repo_root),
    )
    global LAST_HELPER_WARNING
    LAST_HELPER_WARNING = warning
    print(warning, file=sys.stderr)


def _handle_backend_command_failure(
    repo_root: Path,
    hook: str,
    payload: dict,
    completed: subprocess.CompletedProcess,
) -> None:
    detail = ((completed.stdout or "") + (completed.stderr or "")).strip()
    _append_helper_failure(
        repo_root=repo_root,
        payload={
            "hook": hook,
            "category": payload["category"],
            "subject": payload["subject"],
            "message": payload["message"],
            "exception_type": "BackendCommandFailed",
            "traceback": detail[:4000] or f"returncode={completed.returncode}",
            "failed_at": datetime.now(dt_tz.utc).isoformat(),
        },
    )
    warning = (
        f"WARN {hook}: backend command failed while filing finding for "
        f"{payload['subject']}. Logged to audit/helper_failures.jsonl."
    )
    global LAST_HELPER_WARNING
    LAST_HELPER_WARNING = warning
    print(warning, file=sys.stderr)


def _validate_finding_inputs(category: str, severity: str, subject: str, message: str) -> None:
    if not category.strip():
        raise ValueError("category must not be empty")
    if severity not in _FINDING_SEVERITIES:
        raise ValueError("severity must be one of low, medium, high, critical")
    if not subject.strip() or not _SUBJECT_RE.match(subject):
        raise ValueError("subject must use file:line shape")
    if len(message.strip()) < 20:
        raise ValueError("message must be at least 20 characters")


def _buffer_finding(payload: dict, *, repo_root: Path, agent: str = "codex") -> None:
    audit_dir = repo_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    line = {
        "category": payload["category"],
        "severity": payload["severity"],
        "subject": payload["subject"],
        "message": payload["message"],
        "buffered_at": datetime.now(dt_tz.utc).isoformat(),
        "agent": agent,
    }
    data = (json.dumps(line, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    fd = os.open(audit_dir / "findings_buffer.jsonl", flags, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def _recent_crash_count(*, repo_root: Path) -> int:
    cutoff = datetime.now(dt_tz.utc) - _HELPER_CRASH_WINDOW
    count = 0
    for entry in _iter_helper_failures(repo_root):
        failed_at = parse_iso8601(str(entry.get("failed_at", "")))
        if failed_at is not None and failed_at >= cutoff:
            count += 1
    return count


def _latest_crash_summary(*, repo_root: Path) -> str:
    latest = None
    for entry in _iter_helper_failures(repo_root):
        latest = entry
    if not latest:
        return "unknown"
    return str(latest.get("exception_type") or "unknown exception")[:120]


def _iter_helper_failures(repo_root: Path):
    path = repo_root / "audit" / "helper_failures.jsonl"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _log_helper_failure(
    *,
    repo_root: Path,
    hook: str,
    category: str,
    subject: str,
    message: str,
    exc: Exception,
) -> None:
    payload = {
        "hook": hook,
        "category": category,
        "subject": subject,
        "message": message,
        "exception_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
        "failed_at": datetime.now(dt_tz.utc).isoformat(),
    }
    _append_helper_failure(repo_root=repo_root, payload=payload)


def _append_helper_failure(*, repo_root: Path, payload: dict) -> None:
    audit_dir = repo_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(audit_dir / "helper_failures.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def _format_helper_warning(hook: str, subject: str, count: int) -> str:
    return (
        f"WARN {hook}: helper crashed while filing finding for {subject}. "
        f"Logged to audit/helper_failures.jsonl. {count} crashes in last 60 minutes."
    )


def _parse_autoissue_id(stdout: str) -> int | None:
    match = re.search(r"AutoIssue=#(\d+)", stdout or "")
    if not match:
        return None
    return int(match.group(1))


def derive_concept_tags(category: str, subject: str) -> list[str]:
    path = subject.split(":", 1)[0].replace("\\", "/")
    parts = [part for part in path.split("/")[:-1] if part and part != "apps"]
    tags = {category.split("_", 1)[0], *parts}
    return sorted(tags)


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
