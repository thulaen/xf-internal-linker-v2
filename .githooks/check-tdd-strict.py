#!/usr/bin/env python3
"""PARAMOUNT — Strict TDD with Lesson Evidence (slice 1.6+, added 2026-05-17).

Hard-blocks any code-changing commit whose staged AGENT-HANDOFF.md entry
does not include `[TDD CYCLE STRICT: ...]` markers proving every touched
production source file went through a real Red→Green→Refactor cycle plus
had its lesson logged as an AutoIssue(category='tdd_lesson').

Accepted forms:

  Full Red-Green-Refactor:
    [TDD CYCLE STRICT: file=<src> red=<test>:<line>
     red_run_at=<ISO8601> red_result=FAIL
     green=<src>:<line> green_run_at=<ISO8601> green_result=PASS
     refactor="<one-line summary or none>"
     lesson_autoissue=#<N>]

  Refactor-only (no behaviour change):
    [REFACTOR ONLY: file=<src>
     green_run_at=<ISO8601> green_result=PASS
     regression_test=<test>:<line>
     lesson_autoissue=#<N>]

Rule-F compliant. See docs/TDD-STRICT-RULE.md for the full rule.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone as dt_tz
from pathlib import Path
from typing import Any

# Production-source / generated / test patterns + is_production_source +
# parse_iso8601 + the staged-diff reader all live in the shared helpers
# module per paper-trail #585 / test_case #703.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import (  # noqa: E402  (sys.path insert above must precede)
    GENERATED_PATTERNS as _GENERATED_PATTERNS,
    NON_PRODUCTION_EXTENSIONS as _NON_PRODUCTION_EXTENSIONS,
    NON_PRODUCTION_NAMES as _NON_PRODUCTION_NAMES,
    PRODUCTION_PREFIXES as _PRODUCTION_PREFIXES,
    TEST_FILE_PATTERNS as _TEST_FILE_PATTERNS,
    get_staged_handoff_diff,
    is_production_source as _shared_is_production_source,
    parse_iso8601 as _shared_parse_iso8601,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


_STRICT_MARKER_RE = re.compile(
    r"\[TDD\s+CYCLE\s+STRICT:\s*"
    r"file=(?P<file>\S+)\s+"
    r"red=(?P<red>\S+)\s+"
    r"red_run_at=(?P<red_run_at>\S+)\s+"
    r"red_result=(?P<red_result>\S+)\s+"
    r"green=(?P<green>\S+)\s+"
    r"green_run_at=(?P<green_run_at>\S+)\s+"
    r"green_result=(?P<green_result>\S+)\s+"
    r"refactor=\"(?P<refactor>[^\"]*)\"\s+"
    r"lesson_autoissue=#(?P<lesson_autoissue>\d+)\s*\]",
    re.IGNORECASE,
)

_REFACTOR_ONLY_RE = re.compile(
    r"\[REFACTOR\s+ONLY:\s*"
    r"file=(?P<file>\S+)\s+"
    r"green_run_at=(?P<green_run_at>\S+)\s+"
    r"green_result=(?P<green_result>\S+)\s+"
    r"regression_test=(?P<regression_test>\S+)\s+"
    r"lesson_autoissue=#(?P<lesson_autoissue>\d+)\s*\]",
    re.IGNORECASE,
)

# 2026-05-17 — five-layer coverage marker. Required per touched production
# source file alongside [TDD CYCLE STRICT:]. See docs/TDD-STRICT-RULE.md.
# Each field is either a non-negative integer count or `N/A:"<reason>"`.
_COVERAGE_MARKER_RE = re.compile(
    r"\[TDD\s+COVERAGE:\s*"
    r"file=(?P<file>\S+)\s+"
    r"edge_cases=(?P<edge_cases>\d+|N/A:\"[^\"]+\")\s+"
    r"resource_release=(?P<resource_release>\d+|N/A:\"[^\"]+\")\s+"
    r"latency=(?P<latency>\d+|N/A:\"[^\"]+\")\s+"
    r"smoke=(?P<smoke>\d+|N/A:\"[^\"]+\")\s+"
    r"e2e=(?P<e2e>\d+|N/A:\"[^\"]+\")\s*\]",
    re.IGNORECASE,
)

# Trivial-change bypass — REPLACES both [TDD CYCLE STRICT:] and
# [TDD COVERAGE:] for genuinely trivial edits (typo, log message, comment,
# dead import). The reason must be a real sentence ≥ 20 chars.
_TRIVIAL_MARKER_RE = re.compile(
    r"\[TRIVIAL\s+CHANGE:\s*"
    r"file=(?P<file>\S+)\s+"
    r"reason=\"(?P<reason>[^\"]+)\"\s*\]",
    re.IGNORECASE,
)

# Grandfather bypass — REPLACES both markers for files that landed BEFORE
# the strict-TDD rule itself was committed. The strict-TDD rule lives in
# docs/TDD-STRICT-RULE.md; this form is accepted ONLY when that file is
# also in the staged diff (i.e., this commit IS the rule-introduction
# commit). Every grandfathered file MUST cite at least one regression test
# that covers it AND a paper-trail # capturing the back-fill follow-up.
# Once the rule-introduction commit lands, this form is DEAD — touching
# any of these files again requires the full strict marker pair.
_GRANDFATHER_MARKER_RE = re.compile(
    r"\[TDD\s+CYCLE\s+GRANDFATHERED:\s*"
    r"file=(?P<file>\S+)\s+"
    r"reason=\"(?P<reason>[^\"]+)\"\s+"
    r"regression_tests=(?P<regression_tests>\S+)\s+"
    r"follow_up_paper_trail=#(?P<follow_up>\d+)\s*\]",
    re.IGNORECASE,
)
_GRANDFATHER_GATE_FILE = "docs/TDD-STRICT-RULE.md"

# 2026-05-17 — paper-trail #586 / test_case #704.
# Batch-grandfather form for rule-introduction commits that touch many
# files of the same shape. Collapses an N-file marker wall to one
# marker. Accepted ONLY when the matching spec is in the staged diff.
_BATCH_GRANDFATHER_MARKER_RE = re.compile(
    r"\[RULE\s+INTRODUCTION\s+BATCH\s+GRANDFATHERED:\s*"
    r"paper_trail=#(?P<paper_trail>\d+)\s+"
    r"reason=\"(?P<reason>[^\"]+)\"\s+"
    r"files=(?P<glob>\S+?)\s*\]",
    re.IGNORECASE,
)

# Tightness rules for any field that uses N/A:"<reason>" or trivial reasons.
_MIN_JUSTIFICATION_CHARS = 20
_FORBIDDEN_REASONS = (
    "too small to test",
    "obvious",
    "will add a test later",
    "trivial",
    "none",
    "n/a",
    "skip",
    "later",
)


# is_production_source + parse_iso8601 live in _hook_helpers.py per
# paper-trail #585. Re-exposed under the original local names so the
# rest of this module stays unchanged.
is_production_source = _shared_is_production_source
parse_iso8601 = _shared_parse_iso8601


def parse_strict_markers(diff: str) -> list[dict[str, Any]]:
    """Extract every [TDD CYCLE STRICT:] and [REFACTOR ONLY:] marker."""
    out: list[dict[str, Any]] = []
    for m in _STRICT_MARKER_RE.finditer(diff):
        d = dict(m.groupdict())
        d["red_run_at"] = parse_iso8601(d["red_run_at"])
        d["green_run_at"] = parse_iso8601(d["green_run_at"])
        d["lesson_autoissue"] = int(d["lesson_autoissue"])
        d["refactor_only"] = False
        out.append(d)
    for m in _REFACTOR_ONLY_RE.finditer(diff):
        d = dict(m.groupdict())
        d["green_run_at"] = parse_iso8601(d["green_run_at"])
        d["lesson_autoissue"] = int(d["lesson_autoissue"])
        d["refactor_only"] = True
        d["red_result"] = "FAIL"  # synthesised for downstream uniformity
        d["green_result"] = d.get("green_result", "PASS")
        d["red"] = d.get("regression_test")
        d["red_run_at"] = d["green_run_at"]  # placeholder; not compared
        out.append(d)
    return out


def parse_coverage_markers(diff: str) -> dict[str, dict[str, Any]]:
    """Extract every [TDD COVERAGE:] marker, keyed by file."""
    out: dict[str, dict[str, Any]] = {}
    for m in _COVERAGE_MARKER_RE.finditer(diff):
        d = dict(m.groupdict())
        out[d["file"]] = d
    return out


def parse_trivial_markers(diff: str) -> dict[str, str]:
    """Extract every [TRIVIAL CHANGE:] marker, keyed by file → reason."""
    out: dict[str, str] = {}
    for m in _TRIVIAL_MARKER_RE.finditer(diff):
        out[m.group("file")] = m.group("reason")
    return out


def parse_grandfather_markers(diff: str) -> dict[str, dict[str, str]]:
    """Extract every [TDD CYCLE GRANDFATHERED:] marker, keyed by file."""
    out: dict[str, dict[str, str]] = {}
    for m in _GRANDFATHER_MARKER_RE.finditer(diff):
        d = dict(m.groupdict())
        out[d["file"]] = d
    return out


def _is_justification_valid(reason: str) -> tuple[bool, str]:
    """Returns (ok, problem_description). Sentence-shape + length checks."""
    cleaned = reason.strip()
    if len(cleaned) < _MIN_JUSTIFICATION_CHARS:
        return False, (
            f"reason is {len(cleaned)} chars; rule requires "
            f">= {_MIN_JUSTIFICATION_CHARS} chars of plain-English explanation"
        )
    low = cleaned.lower()
    for forbidden in _FORBIDDEN_REASONS:
        if low == forbidden or low.startswith(forbidden + " ") or low.startswith(forbidden + ","):
            return False, (
                f"reason {cleaned!r} matches the forbidden phrase {forbidden!r} — "
                f"every code change deserves a real explanation"
            )
    return True, ""


def _validate_coverage_marker(file: str, cov: dict[str, Any]) -> tuple[int, str]:
    """Returns (exit_code, error_str). 0 on pass."""
    for field in ("edge_cases", "resource_release", "latency", "smoke", "e2e"):
        value = cov.get(field, "")
        if value.startswith("N/A"):
            # Form: N/A:"<reason>"
            # The regex group already includes the quotes — strip them.
            after_colon = value.split(":", 1)[1] if ":" in value else ""
            inner = after_colon.strip().strip('"')
            ok, problem = _is_justification_valid(inner)
            if not ok:
                return 2, (
                    f"FAIL check-tdd-strict: [TDD COVERAGE: file={file}] field "
                    f"{field}=N/A has an insufficient justification: {problem}.\n"
                    f"WHY: PARAMOUNT strict-TDD rule requires every N/A slot in the "
                    f"coverage marker to carry a real plain-English sentence "
                    f"explaining why this test layer is irrelevant for THIS "
                    f"change. Empty / one-word / forbidden justifications mean "
                    f"the rule is being routed around.\n"
                    f"UNBLOCK: rewrite the reason as a real sentence "
                    f"(>= 20 chars) explaining why the layer does not apply, "
                    f"or write the test and replace N/A with the count.\n"
                )
        else:
            try:
                count = int(value)
            except ValueError:
                return 2, (
                    f"FAIL check-tdd-strict: [TDD COVERAGE: file={file}] field "
                    f"{field}={value!r} is neither an integer count nor "
                    f"N/A:\"<reason>\".\n"
                )
            if count < 0:
                return 2, (
                    f"FAIL check-tdd-strict: [TDD COVERAGE: file={file}] field "
                    f"{field}={count} is negative; count must be >= 0.\n"
                )
    return 0, ""


# _read_staged_handoff_diff() and _staged_files() live in _hook_helpers.py
# per paper-trail #585 / test_case #703. The shared get_staged_handoff_diff()
# already filters to added lines and uses utf-8/errors=replace.

def _read_staged_handoff_diff() -> str:
    return get_staged_handoff_diff(REPO_ROOT)


def _staged_files() -> list[str]:
    # Note: original used --diff-filter=ACM (no D). Match that subset by
    # asking the helper for added/modified/deleted and filtering out D.
    # Existing tests assume an ACM result; preserve that.
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _verify_lesson_autoissue(lesson_id: int) -> int:
    """Shell out to manage.py verify_tdd_lesson. Return 0 on pass, 2 on fail."""
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_tdd_lesson", "--id", str(lesson_id),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-tdd-strict: docker is not on PATH. The strict-TDD "
            "rule requires verifying lesson AutoIssues against the live DB; "
            "no skip path exists.\n"
            "UNBLOCK: start Docker Desktop and re-run.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-tdd-strict: verify_tdd_lesson timed out.\n"
            "UNBLOCK: wait for the backend stack to be healthy and re-run.\n"
        )
        return 2
    if result.returncode != 0:
        sys.stderr.write(result.stderr or "")
        return 2
    return 0


def _verify_lesson_autoissues_batch(lesson_ids: set[int]) -> int:
    """Shell out once to verify all lesson AutoIssues. Return 0 on pass."""
    if not lesson_ids:
        return 0
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_tdd_lesson",
    ]
    for lesson_id in sorted(lesson_ids):
        cmd.extend(["--id", str(lesson_id)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-tdd-strict: docker is not on PATH. The strict-TDD "
            "rule requires verifying lesson AutoIssues against the live DB; "
            "no skip path exists.\n"
            "UNBLOCK: start Docker Desktop and re-run.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-tdd-strict: batched verify_tdd_lesson timed out.\n"
            "UNBLOCK: wait for the backend stack to be healthy and re-run.\n"
        )
        return 2
    if result.returncode != 0:
        sys.stderr.write(result.stderr or "")
        return 2
    return 0


def _expand_batch_grandfather(
    diff: str,
    staged_files: list[str],
    production_files: list[str],
) -> tuple[set[str], int]:
    """Parse [RULE INTRODUCTION BATCH GRANDFATHERED:] markers.

    Returns (covered_files, exit_code). Exit 0 means continue; non-zero
    means the hook should fail with the message already written to
    stderr. paper-trail #586 / test_case #704.
    """
    import fnmatch

    batch_markers = list(_BATCH_GRANDFATHER_MARKER_RE.finditer(diff))
    if not batch_markers:
        return set(), 0

    # Gate: at least one docs/*-RULE.md file must be in the staged diff.
    rule_specs_staged = [
        f for f in staged_files
        if f.startswith("docs/") and f.endswith("-RULE.md")
    ]
    if not rule_specs_staged:
        sys.stderr.write(
            "FAIL check-tdd-strict: [RULE INTRODUCTION BATCH GRANDFATHERED:] "
            "markers are present but NO docs/*-RULE.md file is in the staged "
            "diff.\n"
            "WHY: the batch-grandfather form is a one-time bypass accepted "
            "ONLY in a rule-introduction commit. The gate is having the "
            "matching spec staged in the same diff so the form cannot be "
            "abused in ordinary commits.\n"
            "UNBLOCK: either stage docs/TDD-STRICT-RULE.md alongside (only "
            "valid for the rule-introduction commit), OR replace the batch "
            "markers with per-file [TDD CYCLE STRICT:] markers.\n"
        )
        return set(), 2

    covered: set[str] = set()
    for m in batch_markers:
        d = m.groupdict()
        reason = d["reason"]
        ok, problem = _is_justification_valid(reason)
        if not ok:
            sys.stderr.write(
                f"FAIL check-tdd-strict: [RULE INTRODUCTION BATCH "
                f"GRANDFATHERED: paper_trail=#{d['paper_trail']}] reason is "
                f"insufficient: {problem}.\n"
                f"UNBLOCK: rewrite the reason as a real plain-English "
                f"sentence (>= 20 chars) explaining why this glob of files "
                f"is being grandfathered.\n"
            )
            return set(), 2
        glob = d["glob"]
        matches = [
            f for f in production_files
            if fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(f, glob.replace("**/", ""))
        ]
        # Also allow recursive glob like services/x/**/server.go.
        if "**" in glob:
            # Split: prefix**/suffix.
            head, _, tail = glob.partition("**")
            head = head.rstrip("/")
            tail = tail.lstrip("/")
            for f in production_files:
                if head and not f.startswith(head + "/") and not f.startswith(head):
                    continue
                if tail and not fnmatch.fnmatch(f, "*" + tail):
                    continue
                matches.append(f)
        covered.update(matches)

    return covered, 0


def validate_markers(
    diff: str,
    staged_files: list[str],
    lesson_verifier: Any = None,
) -> int:
    """Core logic. Returns 0 on pass, 2 on hard-fail. Exposed for tests.

    `lesson_verifier(lesson_id) -> int` lets tests inject a no-op verifier
    (returning 0) so structural assertions do not require Docker + a live
    AutoIssue row. main() passes the real docker-shelled verifier.
    """
    injected_lesson_verifier = lesson_verifier
    production_files = sorted({f for f in staged_files if is_production_source(f)})
    if not production_files:
        return 0  # docs-only / generated-only commit; no markers required

    markers = parse_strict_markers(diff)
    by_file: dict[str, dict[str, Any]] = {}
    for m in markers:
        by_file[m["file"]] = m
    coverage_by_file = parse_coverage_markers(diff)
    trivial_by_file = parse_trivial_markers(diff)
    grandfather_by_file = parse_grandfather_markers(diff)

    # Grandfather form is accepted ONLY when this commit is the rule-
    # introduction commit (i.e., docs/TDD-STRICT-RULE.md is staged).
    grandfather_gate_active = _GRANDFATHER_GATE_FILE in staged_files
    if grandfather_by_file and not grandfather_gate_active:
        sys.stderr.write(
            "FAIL check-tdd-strict: [TDD CYCLE GRANDFATHERED:] markers are "
            "present but the gate file docs/TDD-STRICT-RULE.md is NOT in the "
            "staged diff.\n"
            "WHY: the grandfather form is a one-time bypass accepted ONLY "
            "in the commit that introduces the strict-TDD rule itself. "
            "After that commit lands, touching a grandfathered file again "
            "requires the full [TDD CYCLE STRICT:] + [TDD COVERAGE:] pair "
            "(or [TRIVIAL CHANGE:] for a real trivial edit).\n"
            "UNBLOCK: either stage docs/TDD-STRICT-RULE.md alongside (only "
            "valid for the actual rule-introduction commit), OR replace the "
            "grandfather markers with proper strict markers by following "
            "Red->Green->Refactor for each touched file.\n"
        )
        return 2

    # Validate grandfather marker contents.
    for file, gf in grandfather_by_file.items():
        ok, problem = _is_justification_valid(gf["reason"])
        if not ok:
            sys.stderr.write(
                f"FAIL check-tdd-strict: [TDD CYCLE GRANDFATHERED: file={file}] "
                f"reason is insufficient: {problem}.\n"
                f"WHY: grandfather marker requires a real plain-English "
                f"sentence (>= 20 chars, not a forbidden phrase) explaining "
                f"why this file is being grandfathered.\n"
                f"UNBLOCK: rewrite the reason as a real explanation of why "
                f"the file shipped without strict-TDD evidence (e.g., \"file "
                f"was added before the strict-TDD rule landed; covered by "
                f"<test path> for behaviour\").\n"
            )
            return 2
        # regression_tests must be a non-empty path (no spaces, ends in
        # .py / .go / .ts / .spec.ts / .test.ts etc) — basic shape check.
        regression = gf["regression_tests"]
        if not regression or regression == "none" or regression == "N/A":
            sys.stderr.write(
                f"FAIL check-tdd-strict: [TDD CYCLE GRANDFATHERED: file={file}] "
                f"regression_tests={regression!r} — the grandfather form "
                f"REQUIRES at least one existing test path proving the file's "
                f"behaviour is covered.\n"
                f"UNBLOCK: cite the test file path (e.g., "
                f"regression_tests=services/sidecars/internal/shared/budget/"
                f"budget_test.go), or write a fresh strict marker if no test "
                f"covers it yet.\n"
            )
            return 2

    # [TRIVIAL CHANGE:] bypasses both strict + coverage requirements for a
    # given file. Validate trivial reasons.
    for file, reason in trivial_by_file.items():
        ok, problem = _is_justification_valid(reason)
        if not ok:
            sys.stderr.write(
                f"FAIL check-tdd-strict: [TRIVIAL CHANGE: file={file}] reason "
                f"is insufficient: {problem}.\n"
                f"WHY: trivial-change bypass requires a real plain-English "
                f"sentence (>= 20 chars, not a forbidden phrase) explaining "
                f"why no test was added. Empty / one-word reasons mean the "
                f"rule is being routed around.\n"
                f"UNBLOCK: rewrite the reason or write the test and switch "
                f"back to the full [TDD CYCLE STRICT:] + [TDD COVERAGE:] "
                f"marker pair.\n"
            )
            return 2

    # 2026-05-17 — paper-trail #586 batch-grandfather form. Collapses
    # an N-file grandfather wall to one marker per rule. Self-limited by
    # the spec-file gate (same as the per-file grandfather form).
    batch_grandfathered, batch_exit = _expand_batch_grandfather(
        diff, staged_files, production_files,
    )
    if batch_exit != 0:
        return batch_exit

    files_needing_strict = [
        f for f in production_files
        if f not in trivial_by_file
        and f not in grandfather_by_file
        and f not in batch_grandfathered
    ]
    missing = [f for f in files_needing_strict if f not in by_file]
    if missing:
        sys.stderr.write(
            "FAIL check-tdd-strict: one or more touched production source "
            "files lack a [TDD CYCLE STRICT: ...] (or [REFACTOR ONLY: ...]) "
            "marker in the staged AGENT-HANDOFF.md diff.\n"
            "WHY: PARAMOUNT strict-TDD rule (docs/TDD-STRICT-RULE.md) requires "
            "one marker per touched production source file proving the Red-"
            "Green-Refactor cycle was followed AND the lesson was logged via "
            "manage.py log_tdd_lesson.\n"
            "UNBLOCK: for each file below, run the Red test first, capture "
            "its timestamp + failure output, write the production code, run "
            "the test again, capture the passing timestamp, then run "
            "`docker compose exec -T backend python manage.py log_tdd_lesson "
            "--file <path> --red-test <path> --red-run-at <ISO8601> "
            "--green-run-at <ISO8601> --trap \"...\" --fix-shape \"...\"` and "
            "paste the returned [TDD CYCLE STRICT: ...] marker into the "
            "handoff entry.\n"
        )
        for f in missing:
            sys.stderr.write(f"  [missing] {f}\n")
        return 2

    # Per-marker sub-field validation.
    for f, m in by_file.items():
        if m["refactor_only"]:
            # Refactor-only path: red_run_at is synthesised; only the lesson
            # AutoIssue + a green_result need checking.
            if m["green_result"].upper() != "PASS":
                sys.stderr.write(
                    f"FAIL check-tdd-strict: refactor-only marker for {f} has "
                    f"green_result={m['green_result']!r}, must be PASS.\n"
                )
                return 2
            continue

        if m["red_result"].upper() != "FAIL":
            sys.stderr.write(
                f"FAIL check-tdd-strict: marker for {f} has red_result="
                f"{m['red_result']!r}; PARAMOUNT strict-TDD rule requires "
                f"red_result=FAIL (the test must have been ACTUALLY RED "
                f"first).\n"
                f"WHY: PASS in the Red slot means the test was never failing "
                f"— that's test-after coverage, not TDD.\n"
                f"UNBLOCK: rerun the test BEFORE writing production code, "
                f"capture its failure timestamp, then update the marker.\n"
            )
            return 2

        if m["green_result"].upper() != "PASS":
            sys.stderr.write(
                f"FAIL check-tdd-strict: marker for {f} has green_result="
                f"{m['green_result']!r}, must be PASS.\n"
            )
            return 2

        if m["red_run_at"] is None or m["green_run_at"] is None:
            sys.stderr.write(
                f"FAIL check-tdd-strict: marker for {f} has unparseable "
                f"red_run_at or green_run_at timestamp.\n"
                f"UNBLOCK: use ISO-8601 (e.g. 2026-05-17T04:01:12Z).\n"
            )
            return 2

        if m["red_run_at"] >= m["green_run_at"]:
            sys.stderr.write(
                f"FAIL check-tdd-strict: marker for {f} has red_run_at "
                f"{m['red_run_at'].isoformat()} >= green_run_at "
                f"{m['green_run_at'].isoformat()}.\n"
                f"WHY: the failing run must happen BEFORE the passing run for "
                f"the cycle to be a real Red-then-Green.\n"
                f"UNBLOCK: rerun the failing test FIRST, capture its timestamp, "
                f"then rerun the passing test and capture that.\n"
            )
            return 2

    # Every non-trivial file ALSO needs a [TDD COVERAGE:] marker per the
    # 5-layer rule (edge_cases / resource_release / latency / smoke / e2e).
    coverage_missing = [
        f for f in files_needing_strict if f not in coverage_by_file
    ]
    if coverage_missing:
        sys.stderr.write(
            "FAIL check-tdd-strict: one or more touched production source "
            "files lack a paired [TDD COVERAGE: ...] marker.\n"
            "WHY: PARAMOUNT strict-TDD rule requires every code-changing "
            "commit to declare its test coverage across five layers "
            "(edge_cases, resource_release, latency, smoke, e2e). The "
            "marker proves the agent considered each layer; N/A slots "
            "are accepted only with a real plain-English reason.\n"
            "UNBLOCK: for each file below, add a [TDD COVERAGE: "
            "file=<src> edge_cases=<N>|N/A:\"<reason>\" "
            "resource_release=<N>|N/A:\"<reason>\" latency=<N>|N/A:\"<reason>\" "
            "smoke=<N> e2e=<N>|N/A:\"<reason>\"] marker to the handoff. "
            "If the change is genuinely trivial (typo, log message, "
            "comment, dead import), use [TRIVIAL CHANGE: file=<src> "
            "reason=\"<>= 20-char explanation\"] instead.\n"
        )
        for f in coverage_missing:
            sys.stderr.write(f"  [missing coverage] {f}\n")
        return 2

    # Validate every coverage marker's content.
    for f, cov in coverage_by_file.items():
        rv, err = _validate_coverage_marker(f, cov)
        if rv != 0:
            sys.stderr.write(err)
            return 2

    # All markers structurally OK — verify lesson AutoIssues. Production
    # hook runs one Docker exec for all unique IDs; tests can inject the
    # older single-ID verifier to keep unit tests pure and fast.
    if injected_lesson_verifier is None:
        lesson_ids = {m["lesson_autoissue"] for m in by_file.values()}
        rv = _verify_lesson_autoissues_batch(lesson_ids)
        if rv != 0:
            sys.stderr.write(
                "FAIL check-tdd-strict: batched lesson AutoIssue verification "
                "failed.\n"
            )
            return 2
    else:
        verify_cache: dict[int, int] = {}
        for f, m in by_file.items():
            lesson_id = m["lesson_autoissue"]
            rv = verify_cache.get(lesson_id)
            if rv is None:
                rv = injected_lesson_verifier(lesson_id)
                verify_cache[lesson_id] = rv
            if rv != 0:
                sys.stderr.write(
                    f"FAIL check-tdd-strict: lesson AutoIssue verification "
                    f"failed for {f} (lesson_autoissue=#{lesson_id}).\n"
                )
                return 2

    return 0


def main() -> int:
    files = _staged_files()
    if not files:
        return 0
    diff = _read_staged_handoff_diff()
    return validate_markers(diff, files)


if __name__ == "__main__":
    sys.exit(main())
