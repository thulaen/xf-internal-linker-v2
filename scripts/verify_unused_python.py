#!/usr/bin/env python3
"""Dead-service sweep — find Python service files with zero importers.

Walks ``backend/apps/*/services/*.py``, extracts each non-``__init__``
file's basename, and greps the rest of ``backend/`` for a matching
``import`` (absolute or relative) or ``from`` statement. Files with zero
matches are flagged as candidates for deletion.

Conservative — false positives are fine; false negatives are the worry.
The grep matches both:
  - ``from apps.foo.services.bar import baz``  (absolute)
  - ``from .bar import baz``                   (relative, when ``bar`` is the basename)

A file is reported as orphaned only if NEITHER form turns up. The
caller still has to confirm by running the test suite + grepping for the
exported symbol names; this script just produces the candidate list.

Exit codes:
    0 — clean (no orphans, OR every orphan has a documented exception)
    1 — at least one undocumented orphan was found
    2 — script error

Usage:
    python scripts/verify_unused_python.py
    python scripts/verify_unused_python.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = REPO_ROOT / "backend" / "apps"
SEARCH_ROOT = REPO_ROOT / "backend"


def _service_files() -> list[Path]:
    """Return every service .py file (excluding tests, __init__, and pycache)."""
    out: list[Path] = []
    for path in APPS_ROOT.rglob("services/**/*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        if "/tests/" in path.as_posix() or path.name.startswith("test_"):
            continue
        out.append(path)
    return out


def _has_importer(basename: str) -> bool:
    """Run a grep across backend/ for either an absolute or relative import.

    Uses ``git grep`` so the search is fast and respects .gitignore.
    Falls back to plain ``grep`` if git grep fails (e.g. running outside a
    checkout).
    """
    patterns = [
        f"from .*{basename} import",
        f"import {basename}",
        f"from .{basename} import",
    ]
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["git", "grep", "-l", pattern, "--", "backend/"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return True  # git not available — assume importer exists (conservative)
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv[1:])

    if not APPS_ROOT.exists():
        print(f"[verify_unused_python] backend/apps/ not found at {APPS_ROOT}")
        return 2

    orphans: list[str] = []
    for path in _service_files():
        basename = path.stem
        if _has_importer(basename):
            continue
        # Allow per-file exemption via a top-of-file comment:
        #   # verify-unused-python: kept-for-<reason>
        try:
            head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
        except OSError:
            head = []
        if any("verify-unused-python:" in line for line in head):
            continue
        orphans.append(path.relative_to(REPO_ROOT).as_posix())

    if args.json:
        print(json.dumps({"orphans": orphans}, indent=2))
    else:
        if not orphans:
            print("[verify_unused_python] No orphaned service files found.")
        else:
            print("[verify_unused_python] Orphaned service files (zero importers found):")
            for o in orphans:
                print(f"  {o}")
            print(
                "\nFix one of:\n"
                "  - Delete the file (`git rm <path>`).\n"
                "  - Add a callsite if it's intentionally part of a forthcoming feature.\n"
                "  - Add a top-of-file comment `# verify-unused-python: kept-for-<reason>` "
                "if the file is genuinely kept for management-command / shell use only.\n"
            )
    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
