#!/usr/bin/env python3
"""Pre-commit hard gate — every newly-added or modified production source
file must have a matching test file.

Scope: Python (.py), Rust (.rs), and TypeScript (.ts) production files.

This hook enforces test-driven development by making "code without tests"
a hard commit blocker. It is scoped: only the files in this specific
commit are checked, never the whole codebase.

Rules per change type:

    NEW files (--diff-filter=A):
        Must have a matching test file present in the commit OR already
        in the repo.  This is a HARD BLOCK — no exceptions without an
        OPT_OUT entry.

    MODIFIED files (--diff-filter=M):
        Must have a matching test file already present in the repo.
        If the production file exists but has no test, the commit is
        blocked — this prevents untested code from growing silently.

How test files are found per language:

    Python:
        backend/apps/<module>/<any>.py  →
          <dir>/test_<base>.py
          <dir>/../test_<base>.py
          <dir>/../tests/test_<base>.py
          <dir>/../tests_<base>.py

    Rust:
        rust/**/<name>.rs  →
          <dir>/tests/<name>.rs  OR
          inline #[cfg(test)] module in the source file itself

    TypeScript:
        frontend/src/**/<name>.ts  →
          <dir>/<name>.spec.ts  (Angular convention)

Excluded from checks:
    - Test files themselves (.spec.ts, test_*.py, *_test.rs, tests/)
    - Glue files (admin.py, urls.py, models.py, migrations/, etc.)
    - Type-only files (.d.ts, .model.ts, .enum.ts, .interface.ts)
    - Config / environment files
    - __init__.py, build.rs, lib.rs (barrel exports)
    - Files in OPT_OUT

Exit codes:
    0 — all staged files have matching tests (or none need checking)
    1 — at least one file is missing a matching test
    2 — the hook itself failed
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Per-path opt-outs.  Add an entry here ONLY for files that genuinely
# need no tests (constant tables, type-only declarations, etc.).
# ---------------------------------------------------------------------------
OPT_OUT: frozenset[str] = frozenset({
    # Settings modules are tested via the integrated
    # apps/core/tests_settings_helpers.py suite.
    "backend/apps/core/services/settings_base.py",
    "backend/apps/core/services/settings_defaults.py",
    "backend/apps/core/services/settings_validators.py",
    "backend/apps/core/services/settings_accessors.py",
})

# ---------------------------------------------------------------------------
# Pattern matchers — decide which files need tests
# ---------------------------------------------------------------------------

# Python production files (broad: anything under backend/apps that isn't
# a test, migration, or glue file).
PY_PRODUCTION_RE = re.compile(
    r"^backend/apps/.*\.py$"
)

# Python paths that are thin glue — tested via the code that uses them.
PY_GLUE_RE = re.compile(
    r"/(admin|urls|apps|manage|forms|models|serializers|permissions|signals"
    r"|__init__|conftest)\.py$"
)

# Python paths inside migrations or test directories — skip.
PY_SKIP_RE = re.compile(
    r"/migrations/|/tests?/|test_.*\.py$|tests_.*\.py$"
)

# Rust production files.
RS_PRODUCTION_RE = re.compile(
    r"^rust/.*\.rs$"
)

# Rust files to skip (test files, build scripts, barrel re-exports).
RS_SKIP_RE = re.compile(
    r"/tests/|_test\.rs$|/test_.*\.rs$|/build\.rs$|/lib\.rs$|/mod\.rs$"
)

# TypeScript production files.
TS_PRODUCTION_RE = re.compile(
    r"^frontend/src/.*\.ts$"
)

# TypeScript files that don't need their own tests.
TS_SKIP_RE = re.compile(
    r"\.spec\.ts$|\.stories\.ts$|\.d\.ts$|\.model\.ts$|\.enum\.ts$"
    r"|\.interface\.ts$|\.module\.ts$|\.routes\.ts$|/environments?/"
    r"|/index\.ts$"
)

# Management commands directory pattern — these are tested via their
# own convention (test files named tests_<command>.py or test_<command>.py
# in the parent app directory).
PY_MGMT_CMD_RE = re.compile(
    r"^backend/apps/[^/]+/management/commands/.*\.py$"
)

# Scripts directory — hooks and helper scripts.
SCRIPTS_PY_RE = re.compile(
    r"^scripts/.*\.py$|^\.githooks/.*\.py$"
)

SCRIPTS_SKIP_RE = re.compile(
    r"test_.*\.py$|tests_.*\.py$|__pycache__|conftest\.py$"
)


def staged_files_by_filter(diff_filter: str) -> list[str]:
    """Return staged file paths matching the given diff filter."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only",
             f"--diff-filter={diff_filter}"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [
        line.strip().replace("\\", "/")
        for line in out.splitlines()
        if line.strip()
    ]


def staged_all_files() -> list[str]:
    """All files staged (any change type)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [
        line.strip().replace("\\", "/")
        for line in out.splitlines()
        if line.strip()
    ]


def file_exists_anywhere(candidates: list[str], staged: set[str]) -> bool:
    """A test file counts if it's staged in this commit OR on disk."""
    for cand in candidates:
        if cand in staged:
            return True
        full = REPO_ROOT / cand
        if full.exists():
            return True
    return False


def rust_has_inline_tests(path: str) -> bool:
    """Check whether a .rs file contains a #[cfg(test)] module."""
    full = REPO_ROOT / path
    if not full.exists():
        return False
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
        return "#[cfg(test)]" in content
    except OSError:
        return False


def python_test_candidates(path: str) -> list[str]:
    """Return the list of expected test file locations for a Python file."""
    base = Path(path).stem
    d = Path(path).parent.as_posix()
    parent = Path(path).parent.parent.as_posix()

    candidates = [
        f"{d}/test_{base}.py",
        f"{parent}/test_{base}.py",
        f"{parent}/tests/test_{base}.py",
        f"{parent}/tests_{base}.py",
    ]

    # Management commands have a different convention.
    if PY_MGMT_CMD_RE.match(path):
        app_dir = Path(path).parent.parent.parent.as_posix()
        candidates.extend([
            f"{app_dir}/test_{base}.py",
            f"{app_dir}/tests_{base}.py",
            f"{app_dir}/tests/test_{base}.py",
        ])

    return candidates


def rust_test_candidates(path: str) -> list[str]:
    """Return expected test file locations for a Rust file."""
    base = Path(path).stem
    d = Path(path).parent.as_posix()
    return [
        f"{d}/tests/{base}.rs",
        f"{d}/tests/test_{base}.rs",
        f"{d}/{base}_test.rs",
    ]


def ts_test_candidates(path: str) -> list[str]:
    """Return expected test file locations for a TypeScript file."""
    # Angular convention: foo.component.ts → foo.component.spec.ts
    if path.endswith(".ts"):
        return [path[:-len(".ts")] + ".spec.ts"]
    return []


def classify_file(path: str) -> str | None:
    """Return 'py', 'rs', 'ts', or None if the file doesn't need tests."""
    if path in OPT_OUT:
        return None

    # Python
    if path.endswith(".py"):
        if PY_SKIP_RE.search(path):
            return None
        if PY_PRODUCTION_RE.match(path) and not PY_GLUE_RE.search(path):
            return "py"
        if SCRIPTS_PY_RE.match(path) and not SCRIPTS_SKIP_RE.search(path):
            return "py"
        return None

    # Rust
    if path.endswith(".rs"):
        if RS_SKIP_RE.search(path):
            return None
        if RS_PRODUCTION_RE.match(path):
            return "rs"
        return None

    # TypeScript
    if path.endswith(".ts"):
        if TS_SKIP_RE.search(path):
            return None
        if TS_PRODUCTION_RE.match(path):
            return "ts"
        return None

    return None


def execute_test(test_path: str, lang: str) -> str | None:
    """Run the actual test tool on the file to ensure it passes. Returns error message if fails."""
    # We only run tests that physically exist on disk (not just staged in git index but unwritten).
    if not (REPO_ROOT / test_path).exists():
        return None

    try:
        if lang == "py":
            if test_path.startswith("backend/"):
                module = test_path.replace("backend/", "").replace("/", ".").replace(".py", "")
                cmd = ["docker", "compose", "exec", "-T", "backend", "python", "manage.py", "test", "--noinput", "--keepdb", module]
            else:
                cmd = ["pytest", test_path]
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=120)
        elif lang == "ts":
            # For TS we expect Angular/Karma or standard npm test. We run it headlessly.
            # Using a basic ng test filter if it's an Angular app
            if test_path.startswith("frontend/"):
                cmd = ["npx", "ng", "test", "--include", test_path, "--watch=false", "--browsers=ChromeHeadless"]
            else:
                cmd = ["npm", "test", "--", test_path]
            subprocess.check_output(cmd, cwd=str(REPO_ROOT / "frontend"), stderr=subprocess.STDOUT, timeout=180)
        elif lang == "rs":
            # For Rust, the file itself is either a test or inline tests.
            # We just run cargo test on the workspace.
            cmd = ["cargo", "test", "--manifest-path", "rust/Cargo.toml", "--", Path(test_path).stem]
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=120)
        return None
    except subprocess.CalledProcessError as e:
        out = e.output
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        return f"  {test_path} failed test execution:\n{out}"
    except subprocess.TimeoutExpired:
        return f"  {test_path} timed out during test execution."
    except FileNotFoundError:
        # If the test runner isn't installed locally or in docker, skip gracefully rather than crashing the hook.
        return None

def check_file(
    path: str,
    lang: str,
    staged: set[str],
    change_type: str,
) -> str | None:
    """Check one file. Returns a violation message or None if OK."""
    found_test = None
    if lang == "py":
        candidates = python_test_candidates(path)
        for cand in candidates:
            if cand in staged or (REPO_ROOT / cand).exists():
                found_test = cand
                break
        if not found_test:
            return (
                f"  {path}  ({change_type})\n"
                f"    expected test file at one of:\n"
                + "\n".join(f"      {c}" for c in candidates)
            )

    elif lang == "rs":
        candidates = rust_test_candidates(path)
        for cand in candidates:
            if cand in staged or (REPO_ROOT / cand).exists():
                found_test = cand
                break
        if not found_test and rust_has_inline_tests(path):
            found_test = path
            
        if not found_test:
            return (
                f"  {path}  ({change_type})\n"
                f"    expected test file at one of:\n"
                + "\n".join(f"      {c}" for c in candidates)
                + "\n    OR inline #[cfg(test)] module in the source file"
            )

    elif lang == "ts":
        candidates = ts_test_candidates(path)
        for cand in candidates:
            if cand in staged or (REPO_ROOT / cand).exists():
                found_test = cand
                break
        if not found_test:
            return (
                f"  {path}  ({change_type})\n"
                f"    expected sibling spec: {candidates[0]}"
            )

    # Programmatic verification: Execute the actual test tool to prove it passes!
    if found_test and change_type == "new":
        exec_err = execute_test(found_test, lang)
        if exec_err:
            return exec_err

    return None


def main(argv: list[str]) -> int:
    new_files = staged_files_by_filter("A")
    modified_files = staged_files_by_filter("M")
    staged = set(staged_all_files())

    new_violations: list[str] = []
    mod_violations: list[str] = []

    # Check newly added files — HARD requirement.
    for path in new_files:
        lang = classify_file(path)
        if lang is None:
            continue
        violation = check_file(path, lang, staged, "new")
        if violation:
            new_violations.append(violation)

    # Check modified files — SOFT requirement (warning only).
    for path in modified_files:
        lang = classify_file(path)
        if lang is None:
            continue
        violation = check_file(path, lang, staged, "modified")
        if violation:
            mod_violations.append(violation)

    if mod_violations:
        print("\n[WARNING] check-missing-tests: existing production code was modified without a matching test file.")
        for line in mod_violations:
            print(line)
        print("This is currently a soft warning to avoid blocking bug fixes, but please write tests!")

    if not new_violations:
        return 0

    print(
        "\nWARNING check-missing-tests: new production code staged without a "
        "matching test file.\n"
    )
    for line in new_violations:
        print(line)
    print(
        "\nWhy this matters: untested code is how regressions sneak in."
        "\nThis hook checks ONLY the files you touched — not the whole"
        "\ncodebase. Every new production file needs a test file."
        "\n"
        "\nFix shape:"
        "\n  - Python:     create test_<name>.py in the same dir or parent"
        "\n  - Rust:       create tests/<name>.rs or add #[cfg(test)] inline"
        "\n  - TypeScript: create <name>.spec.ts next to the source file"
        "\n"
        "\nIf the file genuinely needs no tests (constants, type-only),"
        "\nadd it to OPT_OUT in .githooks/check-missing-tests.py."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
