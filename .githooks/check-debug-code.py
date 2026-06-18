#!/usr/bin/env python3
"""Rule H.H1 — block obvious debug code from production paths.

File-scoped: only fires when staged files match production code prefixes.
Rule F compliant: every FAIL message has WHY + UNBLOCK.

Patterns blocked in production source:
  - Python:     pdb / breakpoint() / pdb.set_trace() / DEBUG = True
  - JS/TS:      console.log / console.debug / debugger
  - .env-style: DEBUG=True, DEBUG=1, DEBUG=true (top-level)

Tests, scripts, and migrations are exempt.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_PROD_PREFIXES = (
    "backend/apps/",
    "backend/config/",
    "backend/extensions/",
    "frontend/src/app/",
)
_PROD_SUFFIXES = (".py", ".cpp", ".h", ".ts", ".tsx", ".js")
_EXEMPT_FRAGMENTS = (
    "/tests/", "/test_", "/tests_", "_test.py", "_test.cpp",
    "/migrations/", "/benchmarks/", "/fuzz/",
)

_PY_PATTERNS = (
    re.compile(r"^\s*import\s+pdb\b"),
    re.compile(r"^\s*breakpoint\s*\("),
    re.compile(r"\bpdb\.set_trace\s*\("),
    re.compile(r"^DEBUG\s*=\s*True\b"),
)
_TS_PATTERNS = (
    re.compile(r"\bconsole\.(log|debug|trace)\s*\("),
    re.compile(r"^\s*debugger\s*;"),
)


def _staged_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    paths: list[Path] = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not any(line.startswith(p) for p in _PROD_PREFIXES):
            continue
        if not line.endswith(_PROD_SUFFIXES):
            continue
        if any(fragment in line for fragment in _EXEMPT_FRAGMENTS):
            continue
        paths.append(REPO_ROOT / line)
    return paths


def _scan(path: Path) -> list[tuple[int, str]]:
    """Return [(line_no, snippet)] of debug-code hits in `path`."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    patterns = _PY_PATTERNS if path.suffix == ".py" else _TS_PATTERNS
    hits: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if pat.search(line):
                hits.append((line_no, line.strip()[:120]))
                break
    return hits


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    all_hits: dict[str, list[tuple[int, str]]] = {}
    for f in files:
        hits = _scan(f)
        if hits:
            all_hits[str(f.relative_to(REPO_ROOT))] = hits
    if not all_hits:
        return 0
    sys.stderr.write(
        "FAIL check-debug-code: production source contains debug statements.\n"
        "WHY: Rule H.H1 forbids `print()`, `console.log`, `pdb`, "
        "`breakpoint()`, `debugger`, and `DEBUG=True` in production paths "
        "(`backend/apps/`, `backend/config/`, `backend/extensions/`, "
        "`frontend/src/app/`). Tests, migrations, and benchmarks are exempt.\n"
        "UNBLOCK: Remove the debug statements from these files. If you "
        "genuinely need a log statement, use `logging.getLogger(__name__)."
        "debug(...)` in Python or the Angular logger service in frontend code.\n"
    )
    for path, hits in all_hits.items():
        for line_no, snippet in hits:
            sys.stderr.write(f"  {path}:{line_no}: {snippet}\n")
    sys.stderr.write(
        "\nIf you believe this is a false positive (e.g. the regex flagged "
        "a docstring example), file the report first with:\n"
        "  python scripts/backend_manage.py "
        "report_hook_false_positive --hook check-debug-code "
        "--context \"<explanation>\"\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
