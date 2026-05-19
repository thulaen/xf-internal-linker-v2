#!/usr/bin/env python3
"""PARAMOUNT — No-parallel-quality enforcement (added 2026-05-18).

Hard-blocks any commit that introduces or modifies a quality-orchestration
script in a way that violates the local test resource policy:

> Local quality gates must run sequentially. Agents must not run
> multiple heavy quality tools at the same time.
>
> Forbidden:
>   - running backend tests and frontend tests at the same time locally
>   - running coverage and mutation at the same time locally
>   - running multiple commands at the same time
>   - running multiple frontend test commands at the same time
>   - starting background test jobs to bypass the gate order

The hook scans the staged versions of `scripts/precommit-docker.sh`,
`scripts/run-*-quality.sh`, and `scripts/run-*-mutation.sh` for any of
these patterns and hard-blocks the commit with a Rule-F three-part
error pointing at the helper at `scripts/_quality_concurrency.sh`.

Detected patterns:

1. Background-job operator on a `bash scripts/run-*-quality.sh` or
   `bash scripts/run-*-mutation.sh` command (`&` at end of line, not
   inside a string).
2. `wait -n` / `wait $!` / `wait <pid>` near a quality script — implies
   the agent backgrounded a job and is rejoining it.
3. `parallel` GNU utility invoking any `run-*-quality.sh` or
   `run-*-mutation.sh`.
4. `docker compose run` without `--name` AND not invoked via the
   `quality_docker_compose_run` helper.
5. Two `docker compose run` invocations in the same `sh -lc` block
   (suggests in-container parallelism).

Allowed exception: a line containing `# no-parallel-quality-skip:
<>=20-char reason>` is grandfathered.

Rule-F compliant.

Source: docs/CI-GATES.md § "Local test resource policy".
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SCAN_PATHS = (
    re.compile(r"^scripts/precommit-docker\.sh$"),
    re.compile(r"^scripts/run-[a-z0-9-]+-quality\.sh$"),
    re.compile(r"^scripts/run-[a-z0-9-]+-mutation\.sh$"),
)

# Forbidden patterns. Each tuple: (compiled regex, human-readable label).
_FORBIDDEN = (
    (
        re.compile(
            r"^\s*(?!#).*\bbash\s+scripts/run-[a-z0-9-]+-(?:quality|mutation)\.sh.*&\s*$"
        ),
        "backgrounded quality/mutation script (trailing '&')",
    ),
    (
        re.compile(r"^\s*(?!#).*\bwait\s+(?:-n|\$!|\$\{[^}]+\}|\d+)"),
        "explicit `wait` near a quality command (implies prior background job)",
    ),
    (
        re.compile(
            r"^\s*(?!#).*\bparallel\b.*\brun-[a-z0-9-]+-(?:quality|mutation)\.sh"
        ),
        "GNU `parallel` invoking quality/mutation scripts",
    ),
)

# `docker compose run` without `--name` AND not the helper's wrappers.
_DOCKER_COMPOSE_RUN = re.compile(r"^\s*(?!#).*\bdocker\s+compose\s+run\b")
_HAS_NAME_FLAG = re.compile(r"--name\s+")
_DOCKER_COMPOSE_RUN_BACKGROUND = re.compile(
    r"^\s*(?!#).*\bdocker\s+compose\s+run\b.*&\s*$"
)

# K5: whitelist of wrapper function names is read from
# scripts/_quality_concurrency_whitelist.txt so adding a new wrapper
# doesn't require editing this hook. Falls back to the original three
# names if the file is missing.
_WHITELIST_PATH = REPO_ROOT / "scripts" / "_quality_concurrency_whitelist.txt"
_FALLBACK_WHITELIST = (
    "quality_docker_compose_run",
    "run_cpp_step",
    "run_go_step",
)


def _load_whitelist() -> tuple[str, ...]:
    if not _WHITELIST_PATH.is_file():
        return _FALLBACK_WHITELIST
    try:
        text = _WHITELIST_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _FALLBACK_WHITELIST
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return tuple(names) if names else _FALLBACK_WHITELIST


def _compile_helper_invocation() -> re.Pattern[str]:
    names = _load_whitelist()
    # Escape each name + join with `|`. \b ensures we match whole words.
    pattern = r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b"
    return re.compile(pattern)


_HELPER_INVOCATION = _compile_helper_invocation()

_SKIP_MARKER = re.compile(
    r"#\s*no-parallel-quality-skip:\s*(?P<reason>.{20,})"
)


def _staged_paths() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]


def _matches_scan(path: str) -> bool:
    return any(pattern.match(path) for pattern in _SCAN_PATHS)


def _violations_in_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_no, label, line_text) for each violation."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    violations: list[tuple[int, str, str]] = []
    docker_run_seen_in_block = 0
    in_sh_lc_block = False
    for idx, raw in enumerate(text.splitlines(), start=1):
        opened_sh_lc_block = False
        if _SKIP_MARKER.search(raw):
            continue
        # Pattern A: backgrounded quality/mutation script
        for pattern, label in _FORBIDDEN:
            if pattern.match(raw):
                violations.append((idx, label, raw.strip()))
        # Pattern B: docker compose run without --name and not via helper
        if _DOCKER_COMPOSE_RUN.match(raw):
            if _DOCKER_COMPOSE_RUN_BACKGROUND.match(raw):
                violations.append(
                    (
                        idx,
                        "backgrounded docker compose run (trailing '&')",
                        raw.strip(),
                    )
                )
            if not _HAS_NAME_FLAG.search(raw) and not _HELPER_INVOCATION.search(raw):
                violations.append(
                    (
                        idx,
                        "docker compose run without --name and not via quality_docker_compose_run",
                        raw.strip(),
                    )
                )
        # Pattern C: two docker compose run in same sh -lc block
        # (block boundary = a line with `sh -lc '` opening or `'` closing)
        if "sh -lc '" in raw:
            in_sh_lc_block = True
            opened_sh_lc_block = True
            docker_run_seen_in_block = 0
        if in_sh_lc_block and _DOCKER_COMPOSE_RUN.match(raw):
            docker_run_seen_in_block += 1
            if docker_run_seen_in_block > 1:
                violations.append(
                    (
                        idx,
                        "two `docker compose run` invocations inside one `sh -lc` block (in-container parallelism)",
                        raw.strip(),
                    )
                )
        # Detect end of sh -lc block. A line that ends in unescaped `'`
        # marks the close. Imperfect but good enough: precommit-docker.sh
        # uses one block at a time.
        if in_sh_lc_block and not opened_sh_lc_block and raw.rstrip().endswith("'"):
            in_sh_lc_block = False
            docker_run_seen_in_block = 0
    return violations


def main() -> int:
    paths = _staged_paths()
    targets = [p for p in paths if _matches_scan(p)]
    if not targets:
        return 0
    any_failures = False
    for path in targets:
        full = REPO_ROOT / path
        if not full.is_file():
            continue
        violations = _violations_in_file(full)
        if not violations:
            continue
        any_failures = True
        sys.stderr.write(
            f"FAIL check-no-parallel-quality: {path} contains forbidden "
            f"parallel-quality patterns.\n"
            f"WHY: local test resource policy forbids running multiple "
            f"heavy quality tools at the same time locally. The 1h17m "
            f"orphan Stryker run on 2026-05-17 came from exactly this "
            f"class of bug — backgrounded jobs + unnamed containers "
            f"that survive TaskStop / Ctrl-C.\n"
        )
        for line_no, label, text in violations:
            sys.stderr.write(f"  line {line_no}: {label}\n")
            sys.stderr.write(f"    {text}\n")
        sys.stderr.write(
            "UNBLOCK: rewrite the violating line(s) to run serially. "
            "Source `scripts/_quality_concurrency.sh` at the top, call "
            "`quality_install_cleanup_trap` + `quality_acquire_tool_lock "
            "<tool>`, and use `--name \"$(quality_docker_container_name "
            "<tool>)\"` on every `docker compose run`. For genuinely "
            "non-parallel patterns the regex misreads, add the inline "
            "marker `# no-parallel-quality-skip: <>=20-char plain "
            "English reason>` on the same line.\n"
        )
    return 2 if any_failures else 0


if __name__ == "__main__":
    sys.exit(main())
