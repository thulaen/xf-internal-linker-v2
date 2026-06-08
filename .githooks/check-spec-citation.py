#!/usr/bin/env python3
"""Pre-commit gate for source-backed specs and code proof."""

from __future__ import annotations

from datetime import date
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEC_CITED_RE = re.compile(
    r"\[SPEC CITED:\s*feature=([^\s]+)\s+kind=(\w+)\s+id=(\S+)\s+verified_at=([^\]]+)\]"
)
_SPEC_FRESHNESS_RE = re.compile(
    r"\[SPEC FRESHNESS:\s*reviewed_at=(?P<reviewed>\d{4}-\d{2}-\d{2})\s+"
    r"next_review=(?P<next>\d{4}-\d{2}-\d{2})\]"
)
_SPEC_PROOF_RE = re.compile(r"\[SPEC PROOF:\s*(?P<body>[^\]]+)\]")
_BDD_PROOF_RE = re.compile(r"\[BDD PROOF:\s*Given .+ When .+ Then .+\]")
_TDD_PROOF_RE = re.compile(r"\[TDD PROOF:\s*(?P<body>[^\]]+)\]")
_SPEC_REVIEW_RE = re.compile(r"\[SPEC CODE REVIEW:\s*(?P<body>[^\]]+)\]")
_SPEC_RESEARCH_RE = re.compile(r"\[SPEC RESEARCH GATE:\s*(?P<body>[^\]]+)\]")
_FIELD_RE = re.compile(r"([a-z_]+)=(\"[^\"]*\"|[^\s\]]+)")

_CODE_PREFIXES = (".githooks/", "backend/", "frontend/", "scripts/", "services/")
_CODE_SUFFIXES = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".go",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".ps1",
    ".html",
    ".scss",
    ".css",
    ".yml",
    ".yaml",
    ".toml",
)
_CODE_CONFIGS = {"docker-compose.yml", "otelcol-config.yaml"}
_SPEC_ROOTS = ("docs/specs/", "docs/prds/", "docs/sdds/")
# 2026-05-17 — paper-trail #586 Phase F warning #5. Rule-introduction
# docs at top-level docs/ follow the *-RULE.md naming convention and
# carry the same SPEC FRESHNESS marker + source citations as
# docs/specs/. Accept them as a valid spec path.
_RULE_DOC_PATTERN = re.compile(r"^docs/[A-Z][A-Z0-9-]*-RULE\.md$")
_SOURCE_KINDS = {"patent", "academic_paper", "technical_literature", "technical_doc"}
_SPEC_PROOF_FIELDS = {"specs", "source_types", "checked_at", "status"}
_TDD_FIELDS = {"before_or_alongside", "tests", "result"}
_REVIEW_FIELDS = {"specs", "result"}
_RESEARCH_FIELDS = {"scope", "specs", "coverage", "gaps", "research"}


def _staged_new_specs() -> list[str]:
    out = _git_output(["diff", "--cached", "--name-only", "--diff-filter=A"])
    return [
        _normalize_path(line)
        for line in (out.stdout or "").splitlines()
        if _is_spec_path(line) and not line.strip().endswith("_spec-template.md")
    ]


def _staged_code_files() -> list[str]:
    output = _git_output(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    return [_normalize_path(line) for line in output.stdout.splitlines() if _is_code_path(line)]


def _staged_handoff_diff() -> str:
    output = _git_output(["diff", "--cached", "--unified=0", "--", "AGENT-HANDOFF.md"])
    return "\n".join(
        line[1:]
        for line in output.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _git_output(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
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
        return subprocess.CompletedProcess(args, 1, "", "")


def _today() -> date:
    return date.today()


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _is_spec_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if not normalized.endswith(".md"):
        return False
    if normalized.startswith(_SPEC_ROOTS):
        return True
    # 2026-05-17 — paper-trail #586 Phase F warning #5. Top-level
    # docs/X-RULE.md is the established naming pattern for PARAMOUNT
    # rule docs (TDD-STRICT-RULE, TEST-CASE-FIRST-RULE,
    # PAPER-TRAIL-EVIDENCE-RULE, etc.). They carry the same SPEC
    # FRESHNESS marker + source citations as docs/specs/.
    return bool(_RULE_DOC_PATTERN.match(normalized))


def _is_code_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if normalized in _CODE_CONFIGS:
        return True
    return normalized.startswith(_CODE_PREFIXES) and normalized.endswith(_CODE_SUFFIXES)


def _parse_fields(body: str) -> dict[str, str]:
    return {key: value.strip('"') for key, value in _FIELD_RE.findall(body)}


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_current_month(value: date) -> bool:
    today = _today()
    return value.year == today.year and value.month == today.month


def _fail_lines(*lines: str) -> int:
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def _fail_text(lines: tuple[str, ...]) -> int:
    return _fail_lines(*lines)


def _validate_new_specs(specs: list[str]) -> list[str]:
    missing: list[str] = []
    for spec in specs:
        path = REPO_ROOT / spec
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        problem = _spec_file_problem(spec, text)
        if problem:
            missing.append(spec)
    return missing


def _spec_file_problem(spec: str, text: str) -> str | None:
    citations = [kind for _, kind, _, _ in _SPEC_CITED_RE.findall(text)]
    if not set(citations).intersection(_SOURCE_KINDS):
        return f"{spec} is not source-backed"
    freshness = _SPEC_FRESHNESS_RE.search(text)
    if not freshness:
        return f"{spec} is missing SPEC FRESHNESS"
    reviewed = _parse_iso_date(freshness.group("reviewed"))
    next_review = _parse_iso_date(freshness.group("next"))
    if not reviewed or not next_review:
        return f"{spec} has invalid SPEC FRESHNESS dates"
    if not _is_current_month(reviewed) or next_review < _today():
        return f"{spec} needs a current-month SPEC FRESHNESS review"
    return None


def _handle_new_spec_failures(specs: list[str]) -> int | None:
    missing = _validate_new_specs(specs)
    if missing:
        joined = ", ".join(missing)
        new_spec_lines = (
            f"WARN check-spec-citation: new spec file(s) without citation: {joined}\n"
            "WHY: Rule C requires every new feature / algorithm / signal / "
            "meta-algorithm parameter to cite at least one patent, DOI, RFC, "
            "stable URL, or technical literature before implementation begins.",
            "WHY: every spec also needs a [SPEC FRESHNESS] marker reviewed "
            "in the current month.",
            "UNBLOCK: For each new spec, add at least one citation in the "
            "form `[SPEC CITED: feature=<id> kind=doi id=<reference> "
            "verified_at=<ISO8601>]` and add `[SPEC FRESHNESS: "
            "reviewed_at=<YYYY-MM-DD> next_review=<YYYY-MM-DD>]`.",
        )
        return _fail_text(new_spec_lines)
    return None


def _missing_code_proof(code_files: list[str]) -> int:
    missing_proof_lines = (
        "WARN check-spec-citation: this commit modifies code but does not "
        "include [SPEC PROOF] in the staged handoff.",
        f"WHY: {len(code_files)} staged code file(s) need a current SDD, PRD, "
        "or technical spec with source citations before commit.",
        "UNBLOCK: stage AGENT-HANDOFF.md with [SPEC PROOF], [BDD PROOF], "
        "[TDD PROOF], and [SPEC CODE REVIEW] markers.",
    )
    return _fail_text(missing_proof_lines)


def _validate_code_gate(handoff: str, code_files: list[str]) -> int | None:
    proof = _SPEC_PROOF_RE.search(handoff)
    if not proof:
        return _missing_code_proof(code_files)
    proof_problem = _proof_problem(_parse_fields(proof.group("body")))
    if proof_problem:
        return _code_gate_failure(proof_problem)
    marker_problem = _required_marker_problem(handoff)
    if marker_problem:
        return _code_gate_failure(marker_problem)
    return _validate_proof_specs(handoff, _parse_fields(proof.group("body")))


def _proof_problem(fields: dict[str, str]) -> str | None:
    missing = _SPEC_PROOF_FIELDS.difference(fields)
    if missing:
        return "SPEC PROOF missing field(s): " + ", ".join(sorted(missing))
    checked_at = _parse_iso_date(fields["checked_at"])
    if not checked_at or not _is_current_month(checked_at):
        return "SPEC PROOF checked_at must be in the current month"
    if fields["status"] not in {"current", "updated"}:
        return "SPEC PROOF status must be current or updated"
    source_types = set(_split_csv(fields["source_types"]))
    if not source_types.intersection(_SOURCE_KINDS):
        return "SPEC PROOF needs a patent, academic_paper, or technical_literature source"
    if not _split_csv(fields["specs"]):
        return "SPEC PROOF needs at least one spec path"
    return None


def _required_marker_problem(handoff: str) -> str | None:
    if not _BDD_PROOF_RE.search(handoff):
        return "BDD PROOF is required for the behavior plan"
    tdd = _TDD_PROOF_RE.search(handoff)
    if not tdd:
        return "TDD PROOF is required for the code tests"
    tdd_problem = _tdd_problem(_parse_fields(tdd.group("body")))
    if tdd_problem:
        return tdd_problem
    if not _SPEC_REVIEW_RE.search(handoff):
        return "SPEC CODE REVIEW is required before commit"
    return None


def _tdd_problem(fields: dict[str, str]) -> str | None:
    missing = _TDD_FIELDS.difference(fields)
    if missing:
        return "TDD PROOF missing field(s): " + ", ".join(sorted(missing))
    if fields["before_or_alongside"] != "yes" or fields["result"] != "passed":
        return "TDD PROOF must say before_or_alongside=yes and result=passed"
    return None


def _validate_proof_specs(handoff: str, proof_fields: dict[str, str]) -> int | None:
    specs = _split_csv(proof_fields["specs"])
    review_problem = _review_problem(handoff, specs)
    if review_problem:
        return _code_gate_failure(review_problem)
    research_problem = _research_problem(handoff, specs)
    if research_problem:
        return _code_gate_failure(research_problem)
    spec_problem = _first_spec_problem(specs)
    if spec_problem:
        return _code_gate_failure(spec_problem)
    return None


def _review_problem(handoff: str, proof_specs: list[str]) -> str | None:
    review = _SPEC_REVIEW_RE.search(handoff)
    fields = _parse_fields(review.group("body")) if review else {}
    missing = _REVIEW_FIELDS.difference(fields)
    if missing:
        return "SPEC CODE REVIEW missing field(s): " + ", ".join(sorted(missing))
    if fields["result"] not in {"matched", "updated"}:
        return "SPEC CODE REVIEW result must be matched or updated"
    if not set(proof_specs).issubset(set(_split_csv(fields["specs"]))):
        return "SPEC CODE REVIEW must cover every spec in SPEC PROOF"
    return None


def _research_problem(handoff: str, proof_specs: list[str]) -> str | None:
    research = _SPEC_RESEARCH_RE.search(handoff)
    if not research:
        return "SPEC RESEARCH GATE is required before code changes"
    fields = _parse_fields(research.group("body"))
    missing = _RESEARCH_FIELDS.difference(fields)
    if missing:
        return "SPEC RESEARCH GATE missing field(s): " + ", ".join(sorted(missing))
    if fields["coverage"] not in {"full", "updated"}:
        return "SPEC RESEARCH GATE coverage must be full or updated"
    if fields["gaps"] not in {"none", "filled"}:
        return "SPEC RESEARCH GATE gaps must be none or filled"
    if not set(proof_specs).issubset(set(_split_csv(fields["specs"]))):
        return "SPEC RESEARCH GATE must cover every spec in SPEC PROOF"
    if (fields["coverage"] == "updated" or fields["gaps"] == "filled") and (
        fields["research"] == "none"
    ):
        return (
            "SPEC RESEARCH GATE research must cite the overall feature, module, "
            "system architecture, rule, ranking weight, algorithm, pipeline, "
            "frontend design, security model, code-review policy, "
            "error-tracking integration, or scalability and regression-risk "
            "plan when gaps were filled"
        )
    return None


def _first_spec_problem(specs: list[str]) -> str | None:
    for spec in specs:
        if not _is_spec_path(spec):
            return f"{spec} must live under docs/specs, docs/prds, or docs/sdds"
        path = REPO_ROOT / spec
        if not path.is_file():
            return f"{spec} does not exist"
        problem = _spec_file_problem(spec, path.read_text(encoding="utf-8", errors="replace"))
        if problem:
            return f"{problem}; the spec must be source-backed and current"
    return None


def _code_gate_failure(problem: str) -> int:
    code_gate_lines = (
        f"WARN check-spec-citation: {problem}.",
        "WHY: code commits need a current SDD, PRD, or technical spec backed "
        "by patents, academic papers, or technical literature.",
        "UNBLOCK: update the related spec, run the focused tests, review the "
        "code against the spec, and stage the required handoff markers.",
    )
    return _fail_text(code_gate_lines)


def main() -> int:
    spec_result = _handle_new_spec_failures(_staged_new_specs())
    if spec_result is not None:
        return spec_result
    code_files = _staged_code_files()
    if not code_files:
        return 0
    return _validate_code_gate(_staged_handoff_diff(), code_files) or 0


if __name__ == "__main__":
    sys.exit(main())
