#!/usr/bin/env python3
"""PARAMOUNT — Mandatory Agent Test Case First Rule (slice 1.6+, added 2026-05-17).

Hard-blocks any commit whose staged AGENT-HANDOFF.md entry does not include
`[TEST CASE MAPPING: ...]` markers proving every touched production source
file has at least one corresponding `AutoIssue(category='test_case',
status='open' or 'resolved')` row that captured the implementation contract
BEFORE the code was written.

Accepted forms:

  Per-file mapping (required for every touched production source):
    [TEST CASE MAPPING: file=<src> test_cases=#<idA>,#<idB>,...]

  One-time bypass at this rule's introduction commit only — accepted ONLY
  when `docs/TEST-CASE-FIRST-RULE.md` is also in the staged diff:
    [TEST CASE GRANDFATHERED: file=<src> follow_up_paper_trail=#<N>]

  Whole-commit bypass when no production source file is staged:
    [NON-CODEBASE-EDIT TASK: reason="<≥ 20-char plain-English explanation>"]

Required summary marker at commit time:
    [TEST CASE COMMIT COMPLIANCE: pass mapping=<n> grandfathered=<n>
     non_codebase=yes|no agent=<name>]

Rule-F compliant — every FAIL message includes WHY (citing this rule) plus
UNBLOCK (exact command).

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Production-source / generated / test patterns + is_production_source +
# the staged-diff reader live in _hook_helpers.py per paper-trail #585 /
# test_case #703. Re-exported under the original module-local names so
# the rest of this hook stays unchanged.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_helpers import (  # noqa: E402
    GENERATED_PATTERNS as _GENERATED_PATTERNS,
    NON_PRODUCTION_EXTENSIONS as _NON_PRODUCTION_EXTENSIONS,
    NON_PRODUCTION_NAMES as _NON_PRODUCTION_NAMES,
    PRODUCTION_PREFIXES as _PRODUCTION_PREFIXES,
    TEST_FILE_PATTERNS as _TEST_FILE_PATTERNS,
    get_staged_handoff_diff,
    is_production_source as _shared_is_production_source,
)


# Marker shapes.
_MAPPING_MARKER_RE = re.compile(
    r"\[TEST\s+CASE\s+MAPPING:\s*"
    r"file=(?P<file>\S+)\s+"
    r"test_cases=(?P<test_cases>[^\]]+?)\s*\]",
    re.IGNORECASE,
)

_GRANDFATHER_MARKER_RE = re.compile(
    r"\[TEST\s+CASE\s+GRANDFATHERED:\s*"
    r"file=(?P<file>\S+)\s+"
    r"follow_up_paper_trail=#(?P<follow_up>\d+)\s*\]",
    re.IGNORECASE,
)

_NON_CODEBASE_MARKER_RE = re.compile(
    r"\[NON-CODEBASE-EDIT\s+TASK:\s*"
    r"reason=\"(?P<reason>[^\"]+)\"\s*\]",
    re.IGNORECASE,
)

_COMPLIANCE_MARKER_RE = re.compile(
    r"\[TEST\s+CASE\s+COMMIT\s+COMPLIANCE:\s*"
    r"(?P<status>pass|fail)\s+"
    r"mapping=(?P<mapping>\d+)\s+"
    r"grandfathered=(?P<grandfathered>\d+)\s+"
    r"non_codebase=(?P<non_codebase>yes|no)\s+"
    r"agent=(?P<agent>\S+)\s*\]",
    re.IGNORECASE,
)

_TEST_CASE_ID_RE = re.compile(r"#(\d+)")
_MIN_REASON_CHARS = 20

# Grandfather-form bypass is accepted ONLY when this file is in the staged
# diff. After the rule-introduction commit lands, future commits cannot use
# the grandfather form because the file is no longer "newly staged".
GRANDFATHER_GATE_FILE = "docs/TEST-CASE-FIRST-RULE.md"

# 2026-05-17 — paper-trail #586 / test_case #704.
# Batch-grandfather form for rule-introduction commits that touch many
# files of the same shape. Collapses an N-file marker wall to one
# marker. Accepted ONLY when at least one docs/*-RULE.md is staged.
_BATCH_GRANDFATHER_MARKER_RE = re.compile(
    r"\[RULE\s+INTRODUCTION\s+BATCH\s+GRANDFATHERED:\s*"
    r"paper_trail=#(?P<paper_trail>\d+)\s+"
    r"reason=\"(?P<reason>[^\"]+)\"\s+"
    r"files=(?P<glob>\S+?)\s*\]",
    re.IGNORECASE,
)


is_production_source = _shared_is_production_source


def _is_batch_reason_valid(reason: str) -> tuple[bool, str]:
    """Mirror of the strict-TDD justification check for the batch form."""
    cleaned = reason.strip()
    if len(cleaned) < _MIN_REASON_CHARS:
        return False, (
            f"reason is {len(cleaned)} chars; rule requires "
            f">= {_MIN_REASON_CHARS} chars of plain-English explanation"
        )
    return True, ""


def _expand_batch_grandfather(
    diff: str,
    staged_files: list[str],
    production_files: list[str],
) -> tuple[set[str], int]:
    """Parse [RULE INTRODUCTION BATCH GRANDFATHERED:] markers.

    Returns (covered_files, exit_code). Exit 0 means continue; non-zero
    means the hook should fail with the message already on stderr.
    paper-trail #586 / test_case #704.
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
            "FAIL check-test-case-mandate: [RULE INTRODUCTION BATCH "
            "GRANDFATHERED:] markers are present but NO docs/*-RULE.md is "
            "in the staged diff.\n"
            "WHY: the batch-grandfather form is a one-time bypass accepted "
            "ONLY in a rule-introduction commit. The gate is having the "
            "matching spec staged in the same diff so the form cannot be "
            "abused in ordinary commits.\n"
            "UNBLOCK: stage docs/TEST-CASE-FIRST-RULE.md alongside (only "
            "valid for the rule-introduction commit), OR replace the batch "
            "markers with per-file [TEST CASE MAPPING:] markers.\n"
        )
        return set(), 2

    covered: set[str] = set()
    for m in batch_markers:
        d = m.groupdict()
        ok, problem = _is_batch_reason_valid(d["reason"])
        if not ok:
            sys.stderr.write(
                f"FAIL check-test-case-mandate: [RULE INTRODUCTION BATCH "
                f"GRANDFATHERED: paper_trail=#{d['paper_trail']}] reason is "
                f"insufficient: {problem}.\n"
                f"UNBLOCK: rewrite the reason as a real plain-English "
                f"sentence (>= 20 chars).\n"
            )
            return set(), 2
        glob = d["glob"]
        matches: list[str] = []
        for f in production_files:
            if fnmatch.fnmatch(f, glob):
                matches.append(f)
                continue
            # Recursive ** support: split into head**tail.
            if "**" in glob:
                head, _, tail = glob.partition("**")
                head = head.rstrip("/")
                tail = tail.lstrip("/")
                if head and not (f.startswith(head + "/") or f.startswith(head)):
                    continue
                if tail and not fnmatch.fnmatch(f, "*" + tail):
                    continue
                matches.append(f)
        covered.update(matches)

    return covered, 0


def _real_case_verifier(test_case_id: int) -> int:
    """Default verifier — shells out to manage.py verify_test_case --id <id>.

    Returns the command's exit code (0 == ok). Tests inject `lambda _id: 0`
    to keep the suite hermetic.
    """
    try:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "backend",
                "python", "manage.py", "verify_test_case",
                "--id", str(test_case_id),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 2


def _real_case_verifier_batch(test_case_ids: set[int]) -> int:
    """Verify all referenced test-case rows with one Docker exec."""
    if not test_case_ids:
        return 0
    cmd = [
        "docker", "compose", "exec", "-T", "backend",
        "python", "manage.py", "verify_test_case",
    ]
    for test_case_id in sorted(test_case_ids):
        cmd.extend(["--id", str(test_case_id)])
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr or "")
        return result.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 2


def _fail_no_mapping(file: str) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: production source `{file}` is staged "
        f"but no `[TEST CASE MAPPING: file={file} test_cases=#A,#B,...]` "
        f"marker references it in the staged AGENT-HANDOFF.md diff.\n"
        f"WHY: PARAMOUNT Mandatory Agent Test Case First Rule "
        f"(docs/TEST-CASE-FIRST-RULE.md) requires every code-changing commit "
        f"to map every touched production file to one or more agent-readable "
        f"test case AutoIssue rows that captured the implementation contract "
        f"BEFORE the code was written. Without the mapping, the next agent "
        f"has no spec to read for this surface.\n"
        f"UNBLOCK: For each touched file, run "
        f"`docker compose exec -T backend python manage.py log_test_case "
        f"--file {file} --title \"...\" --given \"...\" --when \"...\" "
        f"--then \"...\"` BEFORE editing the code. Paste the printed "
        f"`[TEST CASE WRITTEN: AutoIssue=#N ...]` marker into the handoff "
        f"entry, then add `[TEST CASE MAPPING: file={file} test_cases=#N]` "
        f"and re-stage. If this file truly pre-dates this rule (slice-1.6 "
        f"in-flight work only), use the one-time grandfather form "
        f"`[TEST CASE GRANDFATHERED: file={file} follow_up_paper_trail=#<N>]` "
        f"and stage `docs/TEST-CASE-FIRST-RULE.md` in the same commit.\n"
    )
    return 2


def _fail_bad_test_case_ids(file: str, raw: str) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[TEST CASE MAPPING: file={file} "
        f"test_cases={raw}]` has no valid `#<integer>` IDs in test_cases.\n"
        f"WHY: the rule requires at least one real `AutoIssue(category="
        f"'test_case')` row referenced by integer ID. Empty or garbage IDs "
        f"defeat the verifier.\n"
        f"UNBLOCK: file a test case first via `manage.py log_test_case ...`, "
        f"then paste the printed AutoIssue number (e.g. `#601`) into the "
        f"`test_cases=#601` slot.\n"
    )
    return 2


def _fail_missing_autoissue(file: str, test_case_id: int) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[TEST CASE MAPPING: file={file} "
        f"test_cases=#{test_case_id}]` references AutoIssue #{test_case_id} "
        f"but `manage.py verify_test_case --id {test_case_id}` did not "
        f"return a valid `AutoIssue(category='test_case')` row with "
        f"non-empty Given/When/Then.\n"
        f"WHY: the rule requires every referenced ID to resolve to a real "
        f"test_case row. Phantom or wrong-category IDs let agents pretend "
        f"the contract exists when it does not.\n"
        f"UNBLOCK: run `docker compose exec -T backend python manage.py "
        f"log_test_case --file {file} --given ... --when ... --then ...` "
        f"to create a real row, then update the marker with the new ID.\n"
    )
    return 2


def _fail_grandfather_without_spec(file: str) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[TEST CASE GRANDFATHERED: "
        f"file={file} ...]` is present but `{GRANDFATHER_GATE_FILE}` is NOT "
        f"in the staged diff.\n"
        f"WHY: the grandfather form is a one-time bypass accepted ONLY at "
        f"the commit that introduces this rule (i.e., the commit that "
        f"stages the spec file for the first time). Once the rule lands, "
        f"the spec file is in the tree but no longer in `git diff --staged`, "
        f"so the bypass silently disappears.\n"
        f"UNBLOCK: either (a) replace the grandfather marker with a real "
        f"`[TEST CASE MAPPING: file={file} test_cases=#N]` after filing the "
        f"test case via `manage.py log_test_case`, OR (b) stage "
        f"`{GRANDFATHER_GATE_FILE}` if this commit is the rule-introduction "
        f"commit.\n"
    )
    return 2


def _fail_grandfather_no_paper_trail(file: str) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[TEST CASE GRANDFATHERED: "
        f"file={file} ...]` is missing the required "
        f"`follow_up_paper_trail=#<N>` reference.\n"
        f"WHY: every grandfathered file must reference a paper-trail entry "
        f"capturing the back-fill work so future sessions retroactively "
        f"author real test cases. Without the reference the grandfathered "
        f"surface is forgotten.\n"
        f"UNBLOCK: file (or reuse) a paper-trail entry via "
        f"`manage.py defer_work --category tooling_gap --title \"Back-fill "
        f"test case for {file}\" --abstract \"Given ... When ... Then ...\" "
        f"...` and paste its `#N` into the marker.\n"
    )
    return 2


def _fail_non_codebase_with_source(staged_source: list[str]) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[NON-CODEBASE-EDIT TASK: ...]` "
        f"bypass is present but production source file(s) are also staged: "
        f"{', '.join(staged_source[:5])}"
        f"{' …' if len(staged_source) > 5 else ''}.\n"
        f"WHY: the non-codebase bypass is for tasks that truly do not "
        f"change code (docs-only, plan-only, answer-only). Mixing the "
        f"bypass with real source changes lets agents skip the contract "
        f"requirement.\n"
        f"UNBLOCK: either remove the source files from the staged set, OR "
        f"remove the `[NON-CODEBASE-EDIT TASK: ...]` marker and add real "
        f"`[TEST CASE MAPPING: ...]` markers for each touched source file.\n"
    )
    return 2


def _fail_short_reason(reason: str) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[NON-CODEBASE-EDIT TASK: reason="
        f"\"{reason}\"]` reason is only {len(reason)} chars; rule requires "
        f">= {_MIN_REASON_CHARS} chars of plain-English explanation.\n"
        f"WHY: one-word reasons (\"docs\", \"chat\", \"skip\") hide what "
        f"the agent actually did. The rule asks for an explanation the "
        f"next agent can read and trust.\n"
        f"UNBLOCK: rewrite the reason as a real sentence explaining why "
        f"this commit truly does not need test cases.\n"
    )
    return 2


def _fail_compliance_missing() -> int:
    sys.stderr.write(
        "FAIL check-test-case-mandate: required `[TEST CASE COMMIT "
        "COMPLIANCE: pass mapping=<n> grandfathered=<n> non_codebase=yes|no "
        "agent=<name>]` summary marker is missing from the staged "
        "AGENT-HANDOFF.md diff.\n"
        "WHY: the summary marker is the agent's commit-time attestation "
        "that the test case first workflow was followed end to end. Its "
        "absence means the agent never produced the compliance report this "
        "rule requires.\n"
        "UNBLOCK: append a `[TEST CASE COMMIT COMPLIANCE: ...]` line to the "
        "handoff entry with the correct mapping count, grandfathered count, "
        "non_codebase flag, and agent name.\n"
    )
    return 2


def _fail_compliance_fail() -> int:
    sys.stderr.write(
        "FAIL check-test-case-mandate: `[TEST CASE COMMIT COMPLIANCE: fail "
        "...]` is present — the agent itself reports the test case first "
        "rule was not satisfied.\n"
        "WHY: the rule says: if `Commit allowed` is `No`, the agent must "
        "not commit until the report turns green.\n"
        "UNBLOCK: fix the gaps the agent identified, then change the "
        "marker's status to `pass`.\n"
    )
    return 2


def _fail_compliance_count(claim: int, actual: int) -> int:
    sys.stderr.write(
        f"FAIL check-test-case-mandate: `[TEST CASE COMMIT COMPLIANCE: ... "
        f"mapping={claim} ...]` does not match the actual count of "
        f"`[TEST CASE MAPPING: ...]` markers in the staged diff "
        f"(observed: {actual}).\n"
        f"WHY: an incorrect count means the agent's commit report does not "
        f"match the markers actually staged. The hook treats this as a "
        f"protocol violation rather than a typo because it leaves the next "
        f"agent uncertain about what the contract actually covered.\n"
        f"UNBLOCK: edit the compliance marker so mapping=<actual> matches "
        f"the real count of MAPPING markers, then re-stage.\n"
    )
    return 2


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT),
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _read_staged_handoff_diff() -> str:
    """Read the staged AGENT-HANDOFF.md diff (delegates to _hook_helpers)."""
    return get_staged_handoff_diff(REPO_ROOT)


def validate_markers(
    diff: str,
    staged_files: list[str],
    case_verifier: Callable[[int], int] | None = None,
) -> int:
    """Validate the staged AGENT-HANDOFF.md diff against the rule.

    Returns 0 on pass, 2 on fail. `case_verifier` is dependency-injected so
    tests can stub the AutoIssue lookup with a pure function instead of
    shelling out to Django. Production callers pass `None` to get the real
    verifier that shells `manage.py verify_test_case`.
    """
    injected_case_verifier = case_verifier
    if case_verifier is None:
        case_verifier = _real_case_verifier

    # Parse all markers.
    mappings = list(_MAPPING_MARKER_RE.finditer(diff))
    grandfathers = list(_GRANDFATHER_MARKER_RE.finditer(diff))
    non_codebase = list(_NON_CODEBASE_MARKER_RE.finditer(diff))
    compliance = _COMPLIANCE_MARKER_RE.search(diff)

    production_files = [p for p in staged_files if is_production_source(p)]
    has_production = bool(production_files)

    # ----- Non-codebase bypass path ---------------------------------------
    if non_codebase:
        # Reason length check (always applied).
        for m in non_codebase:
            reason = m.group("reason").strip()
            if len(reason) < _MIN_REASON_CHARS:
                return _fail_short_reason(reason)
        # Cannot mix bypass with code changes.
        if has_production:
            return _fail_non_codebase_with_source(production_files)
        # Compliance marker still required.
        if compliance is None:
            return _fail_compliance_missing()
        if compliance.group("status").lower() == "fail":
            return _fail_compliance_fail()
        return 0

    # ----- Code-changing commit path --------------------------------------
    if not has_production:
        # No source files staged and no bypass marker — fine, unless the
        # diff has markers anyway; either way we still want the compliance
        # marker on a real commit. An empty diff is ok.
        if compliance is None and (mappings or grandfathers):
            return _fail_compliance_missing()
        if compliance and compliance.group("status").lower() == "fail":
            return _fail_compliance_fail()
        return 0

    # Compliance marker is mandatory for code-changing commits.
    if compliance is None:
        return _fail_compliance_missing()
    if compliance.group("status").lower() == "fail":
        return _fail_compliance_fail()

    # Compliance count must match the observed MAPPING count.
    claimed_mapping = int(compliance.group("mapping"))
    if claimed_mapping != len(mappings):
        return _fail_compliance_count(claimed_mapping, len(mappings))

    # Grandfather form is accepted ONLY when the gate file is staged.
    spec_staged = GRANDFATHER_GATE_FILE in staged_files
    if grandfathers and not spec_staged:
        return _fail_grandfather_without_spec(grandfathers[0].group("file"))

    # Build the set of files covered by mapping or grandfather markers.
    # Production mode verifies all unique ids in one Docker exec. Tests
    # inject a single-id verifier to keep this hook hermetic.
    mapped_files: set[str] = set()
    ids_to_verify: set[int] = set()
    for m in mappings:
        file = m.group("file")
        raw = m.group("test_cases").strip()
        ids = [int(t) for t in _TEST_CASE_ID_RE.findall(raw)]
        if not ids:
            return _fail_bad_test_case_ids(file, raw)
        # Verify mapped file is actually staged (catches typos / phantom refs).
        if file not in staged_files:
            sys.stderr.write(
                f"FAIL check-test-case-mandate: `[TEST CASE MAPPING: "
                f"file={file} ...]` references a file that is NOT in the "
                f"staged set.\n"
                f"WHY: marker / staging drift produces wrong attestations.\n"
                f"UNBLOCK: either stage `{file}` (if you meant to include "
                f"it) or remove the marker.\n"
            )
            return 2
        ids_to_verify.update(ids)
        mapped_files.add(file)

    if injected_case_verifier is None:
        rc = _real_case_verifier_batch(ids_to_verify)
        if rc != 0:
            bad_id = min(ids_to_verify) if ids_to_verify else 0
            bad_file = mappings[0].group("file") if mappings else "(unknown)"
            return _fail_missing_autoissue(bad_file, bad_id)
    else:
        verify_cache: dict[int, int] = {}
        for m in mappings:
            file = m.group("file")
            raw = m.group("test_cases").strip()
            ids = [int(t) for t in _TEST_CASE_ID_RE.findall(raw)]
            for cid in ids:
                rc = verify_cache.get(cid)
                if rc is None:
                    rc = case_verifier(cid)
                    verify_cache[cid] = rc
                if rc != 0:
                    return _fail_missing_autoissue(file, cid)

    for m in grandfathers:
        file = m.group("file")
        follow = m.group("follow_up")
        if not follow or follow == "0":
            return _fail_grandfather_no_paper_trail(file)
        mapped_files.add(file)

    # 2026-05-17 — paper-trail #586 batch-grandfather form.
    batch_covered, batch_exit = _expand_batch_grandfather(
        diff, staged_files, production_files,
    )
    if batch_exit != 0:
        return batch_exit
    mapped_files.update(batch_covered)

    # Every production source file must be covered.
    uncovered = [p for p in production_files if p not in mapped_files]
    if uncovered:
        return _fail_no_mapping(uncovered[0])

    return 0


def main() -> int:
    files = _staged_files()
    diff = _read_staged_handoff_diff()
    return validate_markers(diff, files, case_verifier=None)


if __name__ == "__main__":
    sys.exit(main())
