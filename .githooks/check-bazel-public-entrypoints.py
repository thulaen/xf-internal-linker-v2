#!/usr/bin/env python3
"""Block public quality entry points that bypass Bazel."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ENTRYPOINTS = (
    ".github/workflows/ci.yml",
    ".github/workflows/ci-language-quality.yml",
    "AGENTS.md",
    "scripts/hook_orchestrator.py",
    "scripts/precommit-docker.sh",
    "scripts/prepush-docker.sh",
    "scripts/verify.ps1",
)
FORBIDDEN_REFS = (
    "scripts/run-python-quality.sh",
    "scripts/run-angular-quality.sh",
    "scripts/run-rust-quality.sh",
    "scripts/run_pytest_on_context.py",
    "scripts/run_lint_on_context.py",
)
REQUIRED_REF = "scripts/bazel_default.py"


def violations(root: Path = ROOT) -> list[str]:
    """Return public entry-point lines that still bypass Bazel."""
    errors: list[str] = []
    for relative in ACTIVE_ENTRYPOINTS:
        path = root / relative
        if not path.exists():
            continue
        errors.extend(_file_violations(path, relative))
    return errors


def _file_violations(path: Path, relative: str) -> list[str]:
    errors: list[str] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if REQUIRED_REF in line:
            continue
        for forbidden in FORBIDDEN_REFS:
            if forbidden in line:
                errors.append(f"{relative}:{line_no}: use scripts/bazel_default.py instead")
    return errors


def main() -> int:
    errors = violations()
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
