#!/usr/bin/env python3
"""Per-staged-file DIFF coverage floor — hard block.

For every staged Python production file, this gate measures whether the lines
this commit ADDS or MODIFIES are exercised by the file's tests (run under
coverage inside the backend container). It does NOT demand whole-file coverage
of large legacy files — only the changed lines must be covered. This is the
standard "new code must be tested" rule (cf. diff-cover) and lets small fixes
land on under-tested legacy files without forcing a whole-file rewrite, while
still blocking genuinely untested new code.

Test discovery: the convention test files next to / at the app root of the
source (tests_<stem>.py, tests/test_<stem>.py, test_<stem>.py) PLUS any test
file staged in the same commit under the same app — so a regression suite added
alongside the fix (even with a descriptive, non-stem name) is honoured.

Non-Python languages (Angular .ts, C++, Go, Rust, Haskell) are covered by
their dedicated quality runners already in scripts/precommit-docker.sh.

Exit codes:
    0 — every staged Python file has its changed executable lines covered
        (or no measurable floor / no changed executable lines).
    1 — a changed line is uncovered, no test was found for changed code, or
        coverage could not be measured.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = REPO_ROOT / "scripts" / "detect_changed_modules.py"

# Parse `coverage report --show-missing`: the trailing column is a comma list
# of line numbers / ranges, e.g. "69-74, 78, 90-92".
_REPORT_ROW_RE = re.compile(
    r"^(?P<name>[\w./\\-]+\.py)\s+\d+\s+\d+\s+(?:\d+\s+\d+\s+)?[\d.]+%\s+(?P<missing>[\d,\s-]*)$",
    re.MULTILINE,
)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@", re.MULTILINE)


def _load_resolver():
    spec = importlib.util.spec_from_file_location("detect_changed_modules", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fail(detail: str) -> int:
    sys.stderr.write(
        "\nFAIL check-per-file-coverage: a changed line is not covered by tests.\n"
        "WHY: every line you ADD or MODIFY in a production file must be exercised "
        "by a test (diff coverage). Untested new code is where regressions hide. "
        "This gate measures only the lines you changed, not the whole legacy file.\n"
        "UNBLOCK: add or extend a test so the listed changed lines run, then "
        "re-stage. Tiers live in coverage-modules.yaml; this gate enforces them "
        "on changed lines.\n"
        f"\nDetail:\n{detail}\n"
    )
    return 1


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _is_production_py(p: str) -> bool:
    if not p.endswith(".py"):
        return False
    if not (p.startswith("backend/apps/") or p.startswith("backend/config/")):
        return False
    return not re.search(r"(^|/)(tests?/|test_|tests_)|/migrations/|/__init__\.py$", p)


def _is_test_py(p: str) -> bool:
    return p.endswith(".py") and bool(re.search(r"(^|/)(test_|tests_)|/tests/", p))


def _app_root(rel: str) -> str | None:
    """Return 'backend/apps/<app>' for a path under it, else None."""
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[:2] == ("backend", "apps"):
        return "/".join(parts[:3])
    if len(parts) >= 2 and parts[0] == "backend" and parts[1] == "config":
        return "backend/config"
    return None


def _changed_lines(rel: str) -> set[int] | None:
    """Return the set of line numbers this commit adds/modifies in *rel*.

    None means a brand-new file (treat every executable line as changed).
    """
    try:
        diff = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "--", rel],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    if "new file mode" in diff[:2000]:
        return None
    changed: set[int] = set()
    for m in _HUNK_RE.finditer(diff):
        start = int(m.group("start"))
        count = int(m.group("count") or "1")
        for ln in range(start, start + count):
            changed.add(ln)
    return changed


def _test_paths_for(rel: str) -> list[str]:
    path = Path(rel)
    stem = path.stem
    found: list[str] = []
    cur = path.parent
    while True:
        for cand in (
            cur / f"tests_{stem}.py",
            cur / "tests" / f"test_{stem}.py",
            cur / f"test_{stem}.py",
        ):
            posix = cand.as_posix()
            if (REPO_ROOT / cand).is_file() and posix not in found:
                found.append(posix)
        parts = cur.parts
        if len(parts) <= 3 or parts[:2] != ("backend", "apps"):
            break
        cur = cur.parent
    # Also honour any test staged in the same app this commit — a regression
    # suite added alongside the fix (even with a descriptive, non-stem name).
    # Shared by check-per-file-coverage AND check-scoped-mutation, so both
    # discover the same tests from one source of truth.
    app = _app_root(rel)
    if app:
        for t in _staged_files():
            if _is_test_py(t) and t.startswith(app + "/") and t not in found:
                found.append(t)
    return found


def _expand_ranges(spec: str) -> set[int]:
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            if lo.isdigit() and hi.isdigit():
                out.update(range(int(lo), int(hi) + 1))
        elif chunk.isdigit():
            out.add(int(chunk))
    return out


def _missing_lines(rel_to_backend: str, test_paths: list[str]) -> set[int] | None:
    """Run the tests under coverage in the backend container; return the set of
    UNCOVERED (missing) line numbers for the file, or None if unmeasurable.

    Uses a unique temporary coverage data file (via COVERAGE_FILE env var) to
    prevent file corruption when multiple coverage containers run concurrently
    (e.g. parallel hook runs or overlapping test sessions sharing the bind-mounted
    backend/ directory). Each invocation writes to /tmp/.cov.<stem> inside the
    container so concurrent runs never clobber each other's .coverage file.
    """
    pytest_args = " ".join(t[len("backend/"):] for t in test_paths)
    # Derive a stable-but-unique data file name from the source file stem so
    # log output is readable and multiple files don't race on the same path.
    stem = rel_to_backend.replace("/", "_").replace(".", "_")
    cov_file = f"/tmp/.cov_{stem}"
    script = (
        f"COVERAGE_FILE={cov_file} python -m coverage erase && "
        f"COVERAGE_FILE={cov_file} python -m coverage run -m pytest {pytest_args} "
        "-p no:randomly -q --no-cov --override-ini='addopts=' >/dev/null 2>&1; "
        f"COVERAGE_FILE={cov_file} python -m coverage report --show-missing --include='{rel_to_backend}*'"
    )
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    try:
        # coverage/pytest live in the backend-quality image (the lean runtime
        # backend deliberately omits them), per the quality-tool-ownership rule.
        proc = subprocess.run(
            ["docker", "compose", "run", "--rm", "-T", "backend-quality",
             "bash", "-lc", script],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=600, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for m in _REPORT_ROW_RE.finditer(proc.stdout):
        if m.group("name").endswith(rel_to_backend.split("/")[-1]):
            return _expand_ranges(m.group("missing"))
    return None


def main() -> int:
    staged = _staged_files()
    production = [p for p in staged if _is_production_py(p)]
    if not production:
        return 0
    resolver = _load_resolver()

    failures: list[str] = []
    for path in production:
        floor = resolver.tier_line_floor(path)
        if floor is None or floor <= 0:
            continue  # smoke tier / no measurable floor — allowed
        changed = _changed_lines(path)
        tests = _test_paths_for(path)
        rel_to_backend = path[len("backend/"):]
        missing = _missing_lines(rel_to_backend, tests) if tests else None
        if missing is None:
            # No tests, or unmeasurable. Only a problem if there ARE changed
            # executable lines that therefore cannot be shown as covered.
            if tests:
                failures.append(f"  {path}: coverage could not be measured")
            else:
                failures.append(
                    f"  {path}: changed code but no test found "
                    f"(add tests_{Path(path).stem}.py or stage a test in the app)"
                )
            continue
        if changed is None:
            # Brand-new file: every missing line is uncovered new code.
            if missing:
                shown = ", ".join(str(n) for n in sorted(missing)[:15])
                failures.append(f"  {path}: new file has uncovered lines {shown}")
            continue
        uncovered_changed = sorted(changed & missing)
        if uncovered_changed:
            shown = ", ".join(str(n) for n in uncovered_changed[:15])
            failures.append(f"  {path}: changed lines not covered: {shown}")

    if failures:
        return _fail("\n".join(failures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
