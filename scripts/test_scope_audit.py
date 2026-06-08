"""Audit tests for scoped quality-wrapper behavior."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

WRAPPERS = [
    "scripts/run-python-quality.sh",
    "scripts/run-angular-quality.sh",
    "scripts/run-cpp-quality.sh",
    "scripts/run-go-quality.sh",
    "scripts/run-cpp-mutation.sh",
    "scripts/run-go-mutation.sh",
    "scripts/run-cpp-tests.sh",
    "scripts/run-cpp-coverage.sh",
    "scripts/run-cpp-sanitizers.sh",
    "scripts/run-cpp-fuzz-smoke.sh",
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
        for wrapper in WRAPPERS
        if not (
            "quality_check_scope_cap" in _read(wrapper)
            or "quality_log_scope_skip" in _read(wrapper)
            or "quality_log_scope_decision" in _read(wrapper)
        )
    ]

    assert missing == []


def test_cpp_fuzz_smoke_skips_rust_ported_targets() -> None:
    text = _read("scripts/run-cpp-fuzz-smoke.sh")
    removed_targets = {
        "fuzz_anchor_self_information",
        "fuzz_compressed_bloom",
        "fuzz_count_min_sketch",
        "fuzz_counting_bloom",
        "fuzz_l2norm",
    }
    listed_targets = set(re.findall(r"\bfuzz_[A-Za-z0-9_]+\b", text))

    assert removed_targets.isdisjoint(listed_targets)


def test_every_raised_cap_has_documented_reason() -> None:
    missing_reason: list[str] = []
    assignment = re.compile(r"^\s*MAX_SCOPE_FILES_[A-Za-z0-9_]+=(?P<value>\d+)", re.MULTILINE)
    defaults = {
        "mutmut": 20,
        "stryker": 20,
        "mull": 7,
        "go_mutesting": 20,
        "pytest": 50,
        "ng_test": 50,
        "ctest": 10,
        "ruff": 200,
        "pylint": 200,
        "bandit": 200,
        "eslint": 200,
        "stylelint": 200,
        "clang_tidy": 50,
        "golangci_lint": 200,
        "coverage": 100,
        "libFuzzer": 5,
        "libfuzzer": 5,
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
