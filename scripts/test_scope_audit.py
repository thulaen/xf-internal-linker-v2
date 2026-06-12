"""Audit tests for scoped quality-wrapper behavior."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# Surviving quality wrappers after the 2026-06 move to a Python + Rust backend.
# The C, C++, Go, Haskell, and Lua wrappers were deleted, so they are no longer
# audited here.
WRAPPERS = [
    "scripts/run-python-quality.sh",
    "scripts/run-angular-quality.sh",
    "scripts/run-rust-quality.sh",
]

# Wrappers that own their scope decision inline (they print a scope-decision line
# via one of the quality_* shell helpers). run-rust-quality.sh delegates scoping
# to commit_scope.py and run-angular-quality.sh is an empty placeholder, so neither
# carries the inline marker and neither belongs in this stricter list.
SCOPE_DECISION_WRAPPERS = [
    "scripts/run-python-quality.sh",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"\bfind\s+\.\s+-name"),
    re.compile(r"--all-files"),
    re.compile(r"whole-tree"),
    re.compile(r"fallback-to-all"),
    re.compile(r"mutate=src/"),
    re.compile(r"for\s+\w+\s+in\s+\$\(ls\s+"),
    re.compile(r"ruff\s+check\s+backend(/|\s|$)"),
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_no_fallback_to_all_in_quality_scripts() -> None:
    offenders: list[str] = []
    for wrapper in WRAPPERS:
        text = _read(wrapper)
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{wrapper}: {pattern.pattern}")

    assert offenders == []


def test_every_wrapper_writes_scope_decision_line() -> None:
    missing = [
        wrapper
        for wrapper in SCOPE_DECISION_WRAPPERS
        if not (
            "quality_check_scope_cap" in _read(wrapper)
            or "quality_log_scope_skip" in _read(wrapper)
            or "quality_log_scope_decision" in _read(wrapper)
        )
    ]

    assert missing == []


def test_every_raised_cap_has_documented_reason() -> None:
    missing_reason: list[str] = []
    assignment = re.compile(r"^\s*MAX_SCOPE_FILES_[A-Za-z0-9_]+=(?P<value>\d+)", re.MULTILINE)
    defaults = {
        "mutmut": 20,
        "stryker": 20,
        "pytest": 50,
        "ng_test": 50,
        "ruff": 200,
        "pylint": 200,
        "bandit": 200,
        "eslint": 200,
        "stylelint": 200,
        "coverage": 100,
    }
    for wrapper in WRAPPERS:
        lines = _read(wrapper).splitlines()
        for index, line in enumerate(lines):
            match_assignment = assignment.search(line)
            if not match_assignment:
                continue
            cap_name = line.split("=", 1)[0].strip().removeprefix("MAX_SCOPE_FILES_")
            default = defaults.get(cap_name)
            if default is not None and int(match_assignment.group("value")) <= default:
                continue
            window = "\n".join(lines[max(0, index - 3) : index + 1])
            match = re.search(r"# cap raised: (?P<reason>.{20,})", window)
            if match is None:
                missing_reason.append(f"{wrapper}:{index + 1}")

    assert missing_reason == []
