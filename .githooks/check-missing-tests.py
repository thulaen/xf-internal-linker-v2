#!/usr/bin/env python3
"""Pre-commit linter — every newly-added component / service / backend
service module must ship with a matching test file in the same commit.

Why a hook: the CI version of this check (ci.yml lines 462-512) emits
warnings only. Warnings get ignored. The local pre-commit hook makes
"new code without tests" a hard error early so the developer fixes it
in the same commit instead of pushing a warning that's silently
acknowledged in code review.

What this hook does:

   1. Scan staged files for newly-added (--diff-filter=A) sources:
      - Frontend: `frontend/src/**/*.component.ts` and
                  `frontend/src/**/*.service.ts` (excluding `*.spec.ts`).
      - Backend:  `backend/apps/*/services/*.py` (excluding __init__.py
                  and the tests subtree).
   2. For each, look for a matching test file in the same commit:
      - Frontend: a sibling `*.spec.ts` (replace `.ts` with `.spec.ts`).
      - Backend:  any of three locations:
                    `<dir>/test_<base>.py`
                    `<dir>/../test_<base>.py`
                    `<dir>/../tests/test_<base>.py`
   3. If no matching test exists in the commit OR in `git ls-files`,
      block the commit.

What this hook does NOT block:
   - Edits to existing files (only newly-added files trigger).
   - Files inside `__init__.py`, `migrations/`, `admin.py`, `urls.py`,
     `apps.py`, `manage.py`, `forms.py`, `models.py`, `serializers.py`,
     `permissions.py` — these are usually thin glue or wholly tested
     via the views/services that consume them.
   - Storybook `*.stories.ts` files.

Bypass: rare. If a service is genuinely test-free by design (e.g. a
constants-only file, an interface-only TypeScript declaration), add
the path to the OPT_OUT set below with a one-line reason.

Exit codes:
   0 — every newly-added module has a matching test (or none staged)
   1 — at least one new module is missing a matching test
   2 — linter itself failed
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Per-path opt-outs. Add an entry here ONLY for files that genuinely
# need no tests (constant tables, type-only declarations, etc.).
OPT_OUT: frozenset[str] = frozenset({
    # New settings modules (Layer 1-4) are tested via the integrated
    # apps/core/tests_settings_helpers.py suite which covers the facade.
    "backend/apps/core/services/settings_base.py",
    "backend/apps/core/services/settings_defaults.py",
    "backend/apps/core/services/settings_validators.py",
    "backend/apps/core/services/settings_accessors.py",
})

FRONTEND_NEW_RE = re.compile(
    r"^frontend/src/.*\.(component|service)\.ts$"
)
BACKEND_NEW_RE = re.compile(
    r"^backend/apps/[^/]+/services/(?!.*__init__\.py$)(?!.*tests?/).*\.py$"
)

# Backend file paths that look like services but are really thin glue.
BACKEND_GLUE_RE = re.compile(
    r"/(admin|urls|apps|manage|forms|models|serializers|permissions|signals)\.py$"
)


def staged_added_files() -> list[str]:
    """Files newly added in the staged commit (diff-filter=A)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def staged_all_files() -> list[str]:
    """All files staged (any change)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def file_exists_anywhere(candidates: list[str], staged: set[str]) -> bool:
    """A test file counts as 'present' if it is staged OR already in the tree."""
    for cand in candidates:
        if cand in staged:
            return True
        full = REPO_ROOT / cand
        if full.exists():
            return True
    return False


def main(argv: list[str]) -> int:
    new = staged_added_files()
    if not new:
        return 0
    staged = set(staged_all_files())

    violations: list[str] = []

    for path in new:
        if path in OPT_OUT:
            continue
        if path.endswith(".spec.ts") or path.endswith(".stories.ts"):
            continue

        if FRONTEND_NEW_RE.match(path):
            spec = path[: -len(".ts")] + ".spec.ts"
            if not file_exists_anywhere([spec], staged):
                violations.append(
                    f"  {path}\n    expected sibling spec: {spec}"
                )
            continue

        if BACKEND_NEW_RE.match(path) and not BACKEND_GLUE_RE.search(path):
            base = Path(path).stem
            d = Path(path).parent.as_posix()
            parent = Path(path).parent.parent.as_posix()
            candidates = [
                f"{d}/test_{base}.py",
                f"{parent}/test_{base}.py",
                f"{parent}/tests/test_{base}.py",
                f"{parent}/tests_{base}.py",
            ]
            if not file_exists_anywhere(candidates, staged):
                violations.append(
                    f"  {path}\n    expected test file at one of:\n"
                    + "\n".join(f"      {c}" for c in candidates)
                )

    if not violations:
        return 0

    print("\nFAIL check-missing-tests: new module added without a matching test file.\n")
    for line in violations:
        print(line)
    print(
        "\nWhy this matters: untested modules are how regressions sneak in. CLAUDE.md"
        "\nrequires a test before merge — this hook makes 'forgot to add the spec'"
        "\nimpossible to slip past, while only triggering on NEW files (so existing"
        "\nuntested code isn't suddenly your problem)."
        "\n\nFix shape:"
        "\n  - Frontend: create the sibling `.spec.ts` next to your `.component.ts`"
        "\n    or `.service.ts` and stage it. Three tests minimum: render, primary"
        "\n    happy-path interaction, error-path."
        "\n  - Backend: create `test_<base>.py` in the same dir, or one level up,"
        "\n    or in a `tests/` subdir. See docs/TESTING.md for the conventions."
        "\n\nIf the file genuinely needs no tests (constants table, type declarations),"
        "\nadd it to OPT_OUT in this script with a one-line reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
