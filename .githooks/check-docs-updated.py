#!/usr/bin/env python3
"""Pre-commit hook: require docs-site updates alongside code changes.

When production source code (backend/, frontend/src/, rust/, scripts/) is
staged, at least one file inside docs-site/ must also be staged. This
ensures documentation stays in sync with every code change.

Exemptions (files that do NOT trigger the docs requirement):
  - Test files: test_*.py, *_test.py, *.spec.ts, conftest.py, tests/ dirs
  - Config-only: .env*, *.yml, *.yaml, root-level *.json
  - CI/CD: .github/workflows/
  - Agent protocol: AGENT-HANDOFF.md, AI-CONTEXT.md, PLAIN-ENGLISH-RULE.md
  - Hook scripts: .githooks/
  - Documentation itself: docs/, docs-site/
  - Migration files: */migrations/*.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# Directories containing production source code
SOURCE_DIRS = (
    "backend/",
    "frontend/src/",
    "rust/",
    "scripts/",
    "services/",
)

# Patterns that are EXEMPT from requiring docs updates
EXEMPT_PATTERNS = [
    # Test files
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"(^|/)[^/]+_test\.py$"),
    re.compile(r"(^|/)conftest\.py$"),
    re.compile(r"(^|/)tests/"),
    re.compile(r"\.spec\.ts$"),
    re.compile(r"\.stories\.ts$"),
    # Config files
    re.compile(r"^\.env"),
    re.compile(r"\.ya?ml$"),
    re.compile(r"^[^/]+\.json$"),  # root-level JSON only
    # CI/CD
    re.compile(r"^\.github/"),
    # Agent protocol files
    re.compile(r"^AGENT-HANDOFF\.md$"),
    re.compile(r"^AI-CONTEXT\.md$"),
    re.compile(r"^PLAIN-ENGLISH-RULE\.md$"),
    re.compile(r"^THINK-BEFORE-YOU-CODE\.md$"),
    re.compile(r"^NO-DUPLICATES\.md$"),
    # Hook scripts themselves
    re.compile(r"^\.githooks/"),
    # Documentation directories (already docs)
    re.compile(r"^docs/"),
    re.compile(r"^docs-site/"),
    # Django migrations
    re.compile(r"/migrations/[^/]+\.py$"),
    # Lock files
    re.compile(r"(package-lock|Cargo\.lock|poetry\.lock)"),
    # Type stubs and declarations
    re.compile(r"\.d\.ts$"),
]


def staged_files() -> list[str]:
    """Return list of staged file paths."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def is_source_file(path: str) -> bool:
    """Check if a file is production source code."""
    return any(path.startswith(d) for d in SOURCE_DIRS)


def is_exempt(path: str) -> bool:
    """Check if a file is exempt from requiring docs updates."""
    return any(pat.search(path) for pat in EXEMPT_PATTERNS)


def is_docs_file(path: str) -> bool:
    """Check if a file is inside the docs-site directory."""
    return path.startswith("docs-site/")


def main(argv: list[str] | None = None) -> int:
    files = staged_files()

    # Find non-exempt source files
    source_files = [
        f for f in files if is_source_file(f) and not is_exempt(f)
    ]

    if not source_files:
        return 0  # No production code changed, no docs needed

    # Check if any docs-site file is also staged
    docs_files = [f for f in files if is_docs_file(f)]

    if docs_files:
        return 0  # Docs are being updated, all good

    print(
        "\nFAIL check-docs-updated: production code was changed without"
        "\nupdating the documentation site.\n"
    )
    print("Source files changed:")
    for f in source_files[:10]:
        print(f"  - {f}")
    if len(source_files) > 10:
        print(f"  ... and {len(source_files) - 10} more")
    print(
        "\nWhy this matters: documentation must be the single source of"
        "\ntruth. Every code change needs a corresponding docs update."
        "\n"
        "\nFix shape:"
        "\n  - Update the relevant page in docs-site/docs/"
        "\n  - If no page exists yet, create one"
        "\n  - Stage the docs file: git add docs-site/..."
        "\n"
        "\nExempt file types (no docs needed):"
        "\n  - Test files, config files, CI/CD, migrations"
        "\n  - Agent protocol files, hook scripts"
        "\n  - Lock files, type declarations"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
