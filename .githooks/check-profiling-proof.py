#!/usr/bin/env python3
"""Pre-commit gate for before-coding profiling proof."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from apps.auto_issues.profiling_proof_shared import (  # noqa: E402
    NATIVE_REWRITE_LABEL,
    NATIVE_REWRITE_REQUIRED_FIELDS,
    PROFILE_GAP_CATEGORIES,
    PROFILE_PROOF_DECISIONS,
)

_PROOF_RE = re.compile(r"\[PROFILING PROOF:\s*(?P<body>[^\]]+)\]")
_HOTSPOT_RE = re.compile(r"\[HOTSPOT OPTIMIZATION:\s*(?P<body>[^\]]+)\]")
_PIPELINE_GAP_RE = re.compile(r"\[PROFILING PIPELINE GAP:\s*(?P<body>[^\]]+)\]")
_NATIVE_REWRITE_RE = re.compile(r"\[NATIVE REWRITE REVIEW:\s*(?P<body>[^\]]+)\]")
_PERFORMANCE_SPEC_RE = re.compile(r"\[PERFORMANCE SPEC:\s*(?P<body>[^\]]+)\]")
_FIELD_RE = re.compile(r"([a-z_]+)=(\"[^\"]*\"|[^\s\]]+)")

_SOURCE_PREFIXES = (
    ".githooks/",
    "backend/apps/",
    "backend/config/",
    "backend/extensions/",
    "frontend/src/",
    "scripts/",
    "services/",
)
_SOURCE_SUFFIXES = (".py", ".cpp", ".h", ".hpp", ".ts", ".tsx", ".js", ".go", ".sh")
_SOURCE_CONFIGS = {"docker-compose.yml", "otelcol-config.yaml"}
_REPAIR_FILES = {
    ".githooks/check-profiling-proof.py",
    ".githooks/test_check_profiling_proof.py",
    "docker-compose.yml",
    "otelcol-config.yaml",
    "backend/apps/auto_issues/management/commands/inspect_profiles.py",
    "backend/apps/auto_issues/tests_inspect_profiles_command.py",
    "scripts/inspect_profiles.py",
    "scripts/precommit-docker.sh",
}
_REQUIRED_PROOF_FIELDS = {"service", "scope", "source", "hotspots", "baseline", "decision"}
_REQUIRED_PERFORMANCE_SPEC_FIELDS = {"sources", "source_types", "tdd", "tests"}
_REQUIRED_HOTSPOT_FIELDS = {
    "name",
    "before",
    "after",
    "improvement",
    "workload",
    "regression_test",
}


def _parse_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in _FIELD_RE.findall(body):
        fields[key] = value.strip('"')
    return fields


def _git_output(args: list[str]) -> str:
    """UTF-8 with replace fallback so Windows locale codec does not choke
    on em-dashes / arrows / curly quotes that appear in handoff entries."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout or ""


def _staged_source_files() -> list[str]:
    output = _git_output(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [_normalize_path(line) for line in output.splitlines() if _is_source(line)]


def _staged_handoff_diff() -> str:
    output = _git_output(["diff", "--cached", "--unified=0", "--", "AGENT-HANDOFF.md"])
    return "\n".join(
        line[1:]
        for line in output.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _is_source(path: str) -> bool:
    normalized = _normalize_path(path)
    name = Path(normalized).name.lower()
    if normalized in _SOURCE_CONFIGS:
        return True
    return (
        normalized.startswith(_SOURCE_PREFIXES)
        and normalized.endswith(_SOURCE_SUFFIXES)
        and not name.startswith("test_")
        and "_test." not in name
        and ".test." not in name
        and ".spec." not in name
    )


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _fail_lines(*lines: str) -> int:
    return _fail("\n".join(lines) + "\n")


def _missing(required: set[str], fields: dict[str, str]) -> set[str]:
    return required.difference(fields)


def _validate_proof(fields: dict[str, str]) -> str | None:
    missing = _missing(_REQUIRED_PROOF_FIELDS, fields)
    if missing:
        return "missing required field(s): " + ", ".join(sorted(missing))
    if fields["source"] != "pyroscope+otel_profiles":
        return "source must be pyroscope+otel_profiles"
    if fields["decision"] not in PROFILE_PROOF_DECISIONS:
        return "decision must be one of: " + ", ".join(sorted(PROFILE_PROOF_DECISIONS))
    return _validate_hotspot_count(fields["hotspots"])


def _validate_hotspot_count(value: str) -> str | None:
    try:
        count = int(value)
    except ValueError:
        return "hotspots must be a number from 0 to 5"
    if count < 0 or count > 5:
        return "hotspots must be a number from 0 to 5"
    return None


def _validate_hotspot_markers(handoff: str) -> str | None:
    for match in _HOTSPOT_RE.finditer(handoff):
        fields = _parse_fields(match.group("body"))
        missing = _missing(_REQUIRED_HOTSPOT_FIELDS, fields)
        if missing:
            return "HOTSPOT OPTIMIZATION missing field(s): " + ", ".join(sorted(missing))
    return None


def _optimized_needs_hotspot(fields: dict[str, str]) -> bool:
    return fields.get("decision") == "optimized" and int(fields.get("hotspots", "0")) > 0


def _not_achievable_needs_rewrite(fields: dict[str, str]) -> bool:
    return fields.get("decision") == "not-achievable" and int(fields.get("hotspots", "0")) > 0


def _needs_performance_spec(handoff: str, source_files: list[str]) -> bool:
    if _PIPELINE_GAP_RE.search(handoff) or _HOTSPOT_RE.search(handoff):
        return True
    if _NATIVE_REWRITE_RE.search(handoff):
        return True
    if any(path in _SOURCE_CONFIGS for path in source_files):
        return True
    return any("profil" in path or "pyroscope" in path or "performance" in path for path in source_files)


def _validate_performance_spec(handoff: str, source_files: list[str]) -> str | None:
    if not _needs_performance_spec(handoff, source_files):
        return None
    match = _PERFORMANCE_SPEC_RE.search(handoff)
    if not match:
        return "profiling or speed work needs a [PERFORMANCE SPEC] marker"
    fields = _parse_fields(match.group("body"))
    missing = _missing(_REQUIRED_PERFORMANCE_SPEC_FIELDS, fields)
    if missing:
        return "PERFORMANCE SPEC missing field(s): " + ", ".join(sorted(missing))
    source_types = set(fields["source_types"].split(","))
    accepted = {"patent", "academic_paper", "technical_doc"}
    if not source_types.intersection(accepted):
        return "PERFORMANCE SPEC needs a patent, academic_paper, or technical_doc source"
    if fields["tdd"] != "yes":
        return "PERFORMANCE SPEC must say tdd=yes"
    return None


def _gap_is_valid(fields: dict[str, str]) -> str | None:
    if not re.search(r"#\d+", fields.get("autoissues", "")):
        return "PROFILING PIPELINE GAP needs at least one AutoIssue id"
    categories = set(fields.get("categories", "").split(","))
    missing = set(PROFILE_GAP_CATEGORIES).difference(categories)
    if missing:
        return "PROFILING PIPELINE GAP missing category: " + ", ".join(sorted(missing))
    return None


def _native_rewrite_is_valid(handoff: str) -> str | None:
    match = _NATIVE_REWRITE_RE.search(handoff)
    if not match:
        return "not-achievable profiling proof needs a [NATIVE REWRITE REVIEW] marker"
    fields = _parse_fields(match.group("body"))
    missing = set(NATIVE_REWRITE_REQUIRED_FIELDS).difference(fields)
    if missing:
        return "NATIVE REWRITE REVIEW missing field(s): " + ", ".join(sorted(missing))
    if not re.search(r"#\d+", fields.get("autoissue", "")):
        return "NATIVE REWRITE REVIEW needs an AutoIssue id"
    if fields.get("label") != NATIVE_REWRITE_LABEL:
        return f"NATIVE REWRITE REVIEW label must be {NATIVE_REWRITE_LABEL}"
    return None


def _all_files_are_profile_repairs(source_files: list[str]) -> bool:
    return bool(source_files) and all(path in _REPAIR_FILES for path in source_files)


def _source_without_handoff(source_files: list[str]) -> int:
    return _fail_lines(
        "FAIL check-profiling-proof: this commit modifies production source "
        f"({len(source_files)} files) but does not stage AGENT-HANDOFF.md.",
        "WHY: every production source change must prove the agent inspected "
        "Pyroscope and OpenTelemetry Profiles before writing code.",
        "UNBLOCK: run the Docker-managed profile inspection command, paste "
        "its [PROFILING PROOF] marker into AGENT-HANDOFF.md, stage the "
        "handoff, and try the commit again.",
    )


def _missing_proof() -> int:
    message = (
        "FAIL check-profiling-proof: AGENT-HANDOFF.md was updated but does "
        "not include a [PROFILING PROOF] marker.",
        "WHY: the before-coding profiling ritual must be auditable for every "
        "production source change.",
        "UNBLOCK: add the required marker with service, scope, source, "
        "hotspots, baseline, and decision fields.",
    )
    return _fail_lines(*message)


def _handle_gap(handoff: str, source_files: list[str]) -> int | None:
    match = _PIPELINE_GAP_RE.search(handoff)
    if not match:
        return None
    problem = _gap_is_valid(_parse_fields(match.group("body")))
    if problem:
        gap_problem = (
            f"FAIL check-profiling-proof: {problem}.",
            "WHY: pipeline gaps must list all repair categories.",
            "UNBLOCK: add the missing category and deduped AutoIssue id, then stage the handoff.",
        )
        return _fail_lines(*gap_problem)
    if _all_files_are_profile_repairs(source_files):
        return 0
    gap_scope = (
        "FAIL check-profiling-proof: a [PROFILING PIPELINE GAP] marker does "
        "not clear unrelated source changes.",
        "WHY: missing OpenTelemetry Profiles blocks unrelated production "
        "source work until the profiling pipeline is repaired.",
        "UNBLOCK: either repair only profiling files in this commit, or add "
        "a real [PROFILING PROOF] from Pyroscope plus OpenTelemetry Profiles.",
    )
    return _fail_lines(*gap_scope)


def _handle_performance_spec(handoff: str, source_files: list[str]) -> int | None:
    problem = _validate_performance_spec(handoff, source_files)
    if not problem:
        return None
    spec_problem = (
        f"FAIL check-profiling-proof: {problem}.",
        "WHY: speed and profiling work must cite patents, academic papers, "
        "or technical docs before implementation.",
        "UNBLOCK: add the source-backed spec marker and keep the TDD proof.",
    )
    return _fail_lines(*spec_problem)


def _handle_proof(handoff: str) -> int:
    proof_match = _PROOF_RE.search(handoff)
    if not proof_match:
        return _missing_proof()
    proof_fields = _parse_fields(proof_match.group("body"))
    problem = _validate_proof(proof_fields)
    if problem:
        proof_problem = (
            f"FAIL check-profiling-proof: [PROFILING PROOF] {problem}.",
            "WHY: the profiling marker must be complete and machine-checkable.",
            "UNBLOCK: rerun the profile inspection command and paste its exact marker.",
        )
        return _fail_lines(*proof_problem)
    problem = _validate_hotspot_markers(handoff)
    if problem:
        hotspot_problem = (
            f"FAIL check-profiling-proof: {problem}.",
            "WHY: changed hotspots need before and after proof.",
            "UNBLOCK: add name, before, after, improvement, workload, and regression_test.",
        )
        return _fail_lines(*hotspot_problem)
    if _optimized_needs_hotspot(proof_fields) and not _HOTSPOT_RE.search(handoff):
        hotspot_missing = (
            "FAIL check-profiling-proof: optimized profiling proof needs a "
            "[HOTSPOT OPTIMIZATION] marker.",
            "WHY: any optimized hotspot needs before and after metrics.",
            "UNBLOCK: add the hotspot marker with workload and regression test.",
        )
        return _fail_lines(*hotspot_missing)
    rewrite_problem = None
    if _not_achievable_needs_rewrite(proof_fields):
        rewrite_problem = _native_rewrite_is_valid(handoff)
    if rewrite_problem:
        rewrite_missing = (
            f"FAIL check-profiling-proof: {rewrite_problem}.",
            "WHY: a native rewrite is allowed only after measured proof shows "
            "the current language path cannot meet the target.",
            "UNBLOCK: add the narrow rewrite evidence, rollback plan, and "
            "performance-native-rewrite AutoIssue id.",
        )
        return _fail_lines(*rewrite_missing)
    return 0


def main() -> int:
    source_files = _staged_source_files()
    if not source_files:
        return 0
    handoff = _staged_handoff_diff()
    if not handoff:
        return _source_without_handoff(source_files)
    spec_result = _handle_performance_spec(handoff, source_files)
    if spec_result is not None:
        return spec_result
    gap_result = _handle_gap(handoff, source_files)
    if gap_result is not None:
        return gap_result
    return _handle_proof(handoff)


if __name__ == "__main__":
    sys.exit(main())
