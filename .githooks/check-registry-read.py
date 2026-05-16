#!/usr/bin/env python3
"""Pre-commit guard for the auto-fix-30-issues rule (raised to 30 on 2026-05-12 when sources extended from 6 to 10; was auto-fix-18 between 2026-05-11 and 2026-05-12).

When an AGENT-HANDOFF.md entry is added or edited in this commit, the new
content MUST include the `[REGISTRY READ: ...]` marker proving the agent
read the open auto-issues list at session-start.

The marker has TWO halves:

1. **Per-source breakdown.** Format:
   `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / <p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / <z> fuzz / <c> contract / <gh> gh_ci), <M> registry`
   The ten per-source numbers must sum to <N>.

2. **Picks.** Format:
   `picked: #<id1>, #<id2>, #<id3> | g: #<id4>, #<id5>, #<id6> | p: #<id7>, #<id8>, #<id9> | t: #<id10>, #<id11>, #<id12> | l: #<id13>, #<id14>, #<id15> | f: #<id16>, #<id17>, #<id18> | m: #<id19>, #<id20>, #<id21> | z: #<id22>, #<id23>, #<id24> | c: #<id25>, #<id26>, #<id27> | gh: #<id28>, #<id29>, #<id30>]`
   Exactly 30 ID tokens (matching `#\\S+`) total — 3 per source × 10 sources.
   The drought-substitution form `t: 0 found + 3 from agent: #..., #..., #... (drought logged: #...)`
   is accepted per-bucket, provided `drought logged: #<id>` is present and
   the total ID count still reaches 30.

No satisfier phrase can replace the picks half. Every new handoff entry
must include 30 real picked AutoIssue IDs. This applies to slices,
multi-bug tasks, Mission A tasks, docs-only tasks, and any other work.

Why a hook instead of a memory rule: agents have repeatedly forgotten to
log new bugs into the registry / auto_issues table even though the rules
exist as text. A hook makes silent skipping impossible.

Do not bypass this hook. A commit request requires the agent to resolve
the 30 picked AutoIssues first, stage the handoff files, and let the
database check pass.

Run manually:
    python .githooks/check-registry-read.py [path/to/AGENT-HANDOFF.md]
"""

from __future__ import annotations

from collections.abc import Callable
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "AGENT-HANDOFF.md"
AI_CONTEXT = REPO_ROOT / "AI-CONTEXT.md"
SESSION_FILES = (HANDOFF, AI_CONTEXT)
CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".mjs",
    ".py",
    ".rs",
    ".scss",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
CODE_FILENAMES = {
    "Dockerfile",
    "Makefile",
}
GENERATED_BUILD_PARTS = {
    "build",
    "build_tests",
    "build_fuzz",
    "build_mull",
    "build_asan",
    "build_msan",
    "build_tsan",
    "build_cov",
    "__pycache__",
}
GENERATED_BINARY_SUFFIXES = {
    ".a",
    ".dll",
    ".dylib",
    ".exe",
    ".lib",
    ".o",
    ".obj",
    ".pyd",
    ".so",
}
TEMP_TEST_ARTIFACT_PARTS = {
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "mutmut-cache",
    "mutation-report",
    "stryker-tmp",
}
TEMP_TEST_ARTIFACT_NAMES = {
    ".coverage",
    "coverage.xml",
}
TEMP_TEST_ARTIFACT_SUFFIXES = {
    ".gcda",
    ".gcno",
    ".prof",
    ".profdata",
    ".profraw",
    ".pprof",
    ".tmp",
}

# The marker header — captures the ten per-source breakdown numbers so
# we can assert they sum to N.  Order: agent / glitchtip / pyroscope /
# tempo / loki / faro / mutation / fuzz / contract / gh_ci (10-source
# ritual extended from 6 sources on 2026-05-12 to include Phase 6 sources).
NEW_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*(?P<n>\d+)\s+open\s*"
    r"\(\s*(?P<a>\d+)\s+agent\s*/\s*"
    r"(?P<g>\d+)\s+glitchtip\s*/\s*"
    r"(?P<p>\d+)\s+pyroscope\s*/\s*"
    r"(?P<t>\d+)\s+tempo\s*/\s*"
    r"(?P<l>\d+)\s+loki\s*/\s*"
    r"(?P<f>\d+)\s+faro\s*/\s*"
    r"(?P<m>\d+)\s+mutation\s*/\s*"
    r"(?P<z>\d+)\s+fuzz\s*/\s*"
    r"(?P<c>\d+)\s+contract\s*/\s*"
    r"(?P<gh>\d+)\s+gh_ci\s*\)",
    re.IGNORECASE,
)
# 4-source marker from the previous (12-pick) era. We REJECT it now
# but report a helpful message pointing at the new 10-source form.
FOUR_SOURCE_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*\d+\s+open\s*"
    r"\(\s*\d+\s+agent\s*/\s*"
    r"\d+\s+glitchtip\s*/\s*"
    r"\d+\s+pyroscope\s*/\s*"
    r"\d+\s+loki\s*\)",
    re.IGNORECASE,
)
# Backwards-compatible pre-2026-05-10 legacy header (3-pick rule).
LEGACY_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*\d+\s+open auto-issues",
    re.IGNORECASE,
)
# Inside the picks half, count IDs of the form #<token>. We require 30.
ID_TOKEN_RE = re.compile(r"#[A-Za-z0-9._-]+")
FORBIDDEN_SATISFIER_RE = re.compile(
    r"auto-fix-(?:3|12|18|30)\s+satisfier",
    re.IGNORECASE,
)
# When the picks span uses drought substitution, this phrase MUST be
# present somewhere in the marker so the next agent can find the logged
# AutoIssue and investigate why the source was empty.
DROUGHT_PHRASE_RE = re.compile(r"drought\s+logged:\s*#\S+", re.IGNORECASE)
# The picks segment of the marker — everything after "picked:" up to
# the closing bracket.
PICKS_SEGMENT_RE = re.compile(
    r"picked:\s*(?P<picks>[^\]]+?)\]",
    re.IGNORECASE | re.DOTALL,
)
# Phase 7 — the second required marker line. Captures the latest 10
# failed GitHub Actions workflow runs from `gh run list --status failure
# --limit 10`. Two valid forms:
#   - populated:  `[CI FAILED RUNS READ: 7 latest — picked: #123, #456]`
#                 (or "0 latest — no failed runs" when the queue is clean)
#   - skipped:    `[CI FAILED RUNS READ: skipped — gh unavailable]`
#                 (or "skipped — gh JSON unparseable")
# The skipped form is accepted so contributors without `gh` aren't blocked.
CI_FAILED_RUNS_RE = re.compile(
    r"\[CI FAILED RUNS READ:\s*(?:\d+\s+latest|skipped)[^\]]*\]",
    re.IGNORECASE,
)
# FR-251 — fourth and fifth required markers (added 2026-05-12). Agents
# must confirm they read the comprehensive AI-CODING-GUIDELINES.md +
# CODE-COVERAGE-RULES.md, and must drain 10 coverage-gap AutoIssues per
# session in addition to the 30-pick auto-issue quota and the 10 latest
# failed CI runs.
GUIDELINES_READ_RE = re.compile(
    r"\[GUIDELINES READ:\s*AI-CODING-GUIDELINES\.md\s*\+\s*docs/CODE-COVERAGE-RULES\.md\s*\]",
    re.IGNORECASE,
)
QUALITY_GATE_READ_RE = re.compile(
    r"\[QUALITY GATE READ:\s*self-written code must pass guidelines,\s*"
    r"tests,\s*coverage,\s*mutation tests,\s*and required check setup before commit\s*\]",
    re.IGNORECASE,
)
QUALITY_GATE_RESULT_RE = re.compile(
    r"\[QUALITY GATE RESULT:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)
QUALITY_REQUIRED_RESULTS = {
    "guidelines": "passed",
    "tests": "passed",
    "coverage": "met",
    "mutation": "passed",
    "check_setup": "passed",
}
SELF_REVIEW_RESULT_RE = re.compile(
    r"\[SELF REVIEW RESULT:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)
SELF_REVIEW_REQUIRED_KEYS = {
    "scope",
    "autoissues",
    "fixes",
    "reuse",
    "shared_library",
    "complexity",
    "tests",
    "coverage",
    "mutation",
    "benchmark",
    "edge_cases",
    "issues",
}
BDD_PROOF_RE = re.compile(
    r"\[BDD PROOF:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE | re.DOTALL,
)
TDD_PROOF_RE = re.compile(
    r"\[TDD PROOF:\s*(?P<body>[^\]]+)\]",
    re.IGNORECASE | re.DOTALL,
)
LESSON_READ_RE = re.compile(
    r"\[(?:RESOLVED HISTORY|AUTOISSUE LESSONS READ):\s*[^\]]+\]",
    re.IGNORECASE,
)
COVERAGE_GAPS_RE = re.compile(
    r"\[COVERAGE GAPS READ:\s*(?:\d+\s+picked(?:\s*\+\s*\d+\s+(?:to file|filed))?|drought)[^\]]*\]",
    re.IGNORECASE,
)
# FR-251 — end-of-slice / end-of-task / end-of-session marker. Required
# in any AGENT-HANDOFF entry that records work performed.
#
# Strengthened 2026-05-12: both `target=` and `actual=` MUST be
# percentages with the `%` symbol. Bad markers the hook rejects:
#   target=Level A actual=8/8
#   target=N/A actual=N/A
# Good markers the hook accepts:
#   target=90% actual=92.5% — met
#   target=75% actual=68.0% — not met — reason
#   target=0% actual=0% — met (no code changes; no coverage applicable)
COVERAGE_SUMMARY_RE = re.compile(
    r"\[COVERAGE SUMMARY:\s*"
    r"target\s*=\s*\d+(?:\.\d+)?\s*%\s+"
    r"actual\s*=\s*\d+(?:\.\d+)?\s*%\s*"
    r"[^\]]*\b(?:met|not met)\b[^\]]*\]",
    re.IGNORECASE,
)
HANDOFF_HEADING_RE = re.compile(
    r"^#\s+(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\b"
)


def _staged_diff_for(path: Path) -> str:
    """Return the staged additions for *path* (lines starting with '+ ').

    Force UTF-8 + `errors='replace'` so Windows hosts (default cp1252)
    don't crash on em-dashes / arrows / non-ASCII glyphs in handoff
    entries. The regex matchers operate on ASCII anchors so a swapped-
    out byte never affects correctness.
    """
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "--", rel],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return ""
    return "\n".join(
        line[1:] for line in out.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _commit_touches_handoff() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return False
    return any(line.strip() == "AGENT-HANDOFF.md" for line in out.splitlines())


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _is_code_file(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    if suffix in CODE_SUFFIXES or name in CODE_FILENAMES:
        return True
    if parts and parts[0] == ".githooks" and suffix not in {".md", ".txt"}:
        return True
    return False


def _staged_code_files() -> list[str]:
    return [path for path in _staged_files() if _is_code_file(path)]


def _is_generated_build_file(path: str) -> bool:
    path_obj = Path(path)
    parts = set(path_obj.parts)
    if parts.intersection(GENERATED_BUILD_PARTS):
        return True
    if path_obj.suffix.lower() in GENERATED_BINARY_SUFFIXES:
        return True
    if path.startswith("backend/extensions/reports/"):
        return True
    return False


def _staged_generated_build_files() -> list[str]:
    return [path for path in _staged_files() if _is_generated_build_file(path)]


def _is_temporary_test_artifact(path: str) -> bool:
    path_obj = Path(path)
    parts = set(path_obj.parts)
    if parts.intersection(TEMP_TEST_ARTIFACT_PARTS):
        return True
    if path_obj.name in TEMP_TEST_ARTIFACT_NAMES:
        return True
    if path_obj.suffix.lower() in TEMP_TEST_ARTIFACT_SUFFIXES:
        return True
    return False


def _staged_temporary_test_artifacts() -> list[str]:
    return [path for path in _staged_files() if _is_temporary_test_artifact(path)]


def _unstaged_session_files() -> list[str]:
    paths = [path.relative_to(REPO_ROOT).as_posix() for path in SESSION_FILES]
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--", *paths],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return []
    return [
        line.strip()
        for line in out.splitlines()
        if line.strip() in {"AGENT-HANDOFF.md", "AI-CONTEXT.md"}
    ]


def _fail(msg: str) -> int:
    sys.stderr.write(f"\n\033[31m[check-registry-read]\033[0m FAIL: {msg}\n")
    return 1


def _validate_no_unstaged_session_files() -> int:
    files = _unstaged_session_files()
    if not files:
        return 0
    listed = ", ".join(files)
    return _fail(
        f"{listed} has unstaged changes. Stage the session files and finish "
        "the 30 picked AutoIssue fixes before committing. Do not unstage "
        "`AGENT-HANDOFF.md` or `AI-CONTEXT.md` to avoid the database check."
    )


def _validate_no_generated_build_files() -> int:
    files = _staged_generated_build_files()
    if not files:
        return 0
    listed = ", ".join(files[:8])
    if len(files) > 8:
        listed += f", and {len(files) - 8} more"
    return _fail(
        "Generated build output or compiled binaries are staged. Build output "
        "must stay in Docker-managed artifact storage, not Git. Unstage these "
        f"files and keep only source, tests, config, and scripts: {listed}"
    )


def _validate_no_temporary_test_artifacts() -> int:
    files = _staged_temporary_test_artifacts()
    if not files:
        return 0
    listed = ", ".join(files[:8])
    if len(files) > 8:
        listed += f", and {len(files) - 8} more"
    return _fail(
        "Temporary test artefacts are staged. Keep failing TDD scratch files, "
        "coverage output, mutation reports, and profile dumps in ignored "
        "disposable paths. Commit only source, small permanent regression tests, "
        f"and useful summaries. Staged temporary artefacts: {listed}"
    )


def _extract_picked_issue_ids(added: str) -> list[str]:
    picks_match = PICKS_SEGMENT_RE.search(added)
    if not picks_match:
        return []
    picks_blob = DROUGHT_PHRASE_RE.sub("", picks_match.group("picks"))
    return [token.removeprefix("#") for token in ID_TOKEN_RE.findall(picks_blob)]


def _validate_marker(added: str) -> int:
    new_match = NEW_MARKER_RE.search(added)
    if not new_match:
        if FOUR_SOURCE_MARKER_RE.search(added):
            return _fail(
                "Found the 4-source / 12-pick `[REGISTRY READ: <N> open "
                "(<a> agent / <g> glitchtip / <p> pyroscope / <l> loki), ...]` "
                "marker. The rule was raised to 18 picks across 6 sources on "
                "2026-05-11, then extended to 30 picks across 10 sources on 2026-05-12.\n"
                "  Expected: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / "
                "<p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / "
                "<z> fuzz / <c> contract / <gh> gh_ci), <M> registry — "
                "picked: #..., #..., #... | g: #..., #..., #... | ... (10 sources total)]`\n"
                "  Run `docker compose exec -T backend python manage.py print_open_issues` "
                "for all ten per-source counts, pick 30 issues (3 per source × 10 sources), and "
                "rewrite the marker."
            )
        if LEGACY_MARKER_RE.search(added):
            return _fail(
                "Found the pre-2026-05-10 legacy `[REGISTRY READ: <N> open auto-issues, "
                "...]` marker. The rule has been raised multiple times since (12 picks on "
                "2026-05-10, 18 picks on 2026-05-11, extended to 10 sources on 2026-05-12).\n"
                "  Expected: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / "
                "<p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / "
                "<z> fuzz / <c> contract / <gh> gh_ci), <M> registry — "
                "picked: #...x3 | g: #...x3 | ... (10 sources, 3 per source = 30 total)]`."
            )
        return _fail(
            "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
            "any `[REGISTRY READ: ...]` marker. The ABSOLUTE rule in CLAUDE.md / "
            "AGENTS.md requires running `manage.py print_open_issues` at session "
            "start and recording the result.\n"
            "  Expected format: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip "
            "/ <p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / "
            "<z> fuzz / <c> contract / <gh> gh_ci), <M> registry — picked: #..., ...]` "
            "(10 sources, 3 per source)"
        )
    a = int(new_match.group("a"))
    g = int(new_match.group("g"))
    p = int(new_match.group("p"))
    t = int(new_match.group("t"))
    loki = int(new_match.group("l"))
    f = int(new_match.group("f"))
    m = int(new_match.group("m"))
    z = int(new_match.group("z"))
    c = int(new_match.group("c"))
    gh = int(new_match.group("gh"))
    n = int(new_match.group("n"))
    total = a + g + p + t + loki + f + m + z + c + gh
    if total != n:
        return _fail(
            f"Per-source counts in `[REGISTRY READ: ...]` do not sum to N: "
            f"{a} agent + {g} glitchtip + {p} pyroscope + {t} tempo + "
            f"{loki} loki + {f} faro + {m} mutation + {z} fuzz + {c} contract + "
            f"{gh} gh_ci = {total}, but the header says {n} open. "
            "Re-run `print_open_issues` and reconcile."
        )
    return 0


def _validate_picks(added: str) -> int:
    if FORBIDDEN_SATISFIER_RE.search(added):
        return _fail(
            "30 real picked issue IDs are required. "
            "Satisfier phrases are no longer accepted."
        )
    picks_match = PICKS_SEGMENT_RE.search(added)
    if not picks_match:
        return _fail(
            "The `[REGISTRY READ: ...]` marker is present but does not include a "
            "`picked: #..., ...]` segment. Need 30 picks total (3 from each of "
            "agent, glitchtip, pyroscope, tempo, loki, faro, mutation, fuzz, "
            "contract, gh_ci). 30 real picked issue IDs are required. "
            "Satisfier phrases are no longer accepted."
        )
    picks_blob = picks_match.group("picks")
    pick_tokens = _picked_id_tokens(picks_blob)
    has_drought_phrase = bool(DROUGHT_PHRASE_RE.search(picks_blob))
    has_substitution_form = bool(re.search(r"\bfrom\s+agent\b", picks_blob, re.IGNORECASE))
    if len(pick_tokens) != 30:
        return _fail(
            f"Expected exactly 30 picked issue IDs in the `picked: ...` segment "
            f"(3 per source × 10 sources). Found {len(pick_tokens)}.\n"
            "  If a per-source bucket was empty at session-start, use the "
            "substitution form: `m: 0 found + 3 from agent: #..., #..., #... "
            "(drought logged: #<id>)` — and file an "
            "`AutoIssue(kind='picker_drought', source='agent')` for that source so the next agent "
            "investigates."
        )
    if len(set(pick_tokens)) != len(pick_tokens):
        return _fail(
            "Duplicate picked AutoIssue IDs are not allowed in the "
            "`[REGISTRY READ: ...]` marker. Pick 30 different issue IDs."
        )
    if has_substitution_form and not has_drought_phrase:
        return _fail(
            "Substitution form `+ K from agent:` is present but the required "
            "`(drought logged: #<id>)` phrase is missing. File an "
            "`AutoIssue(kind='picker_drought', source='agent')` for the dry "
            "source and reference its id in the marker."
        )
    return 0


def _picked_id_tokens(picks_blob: str) -> list[str]:
    without_drought_refs = DROUGHT_PHRASE_RE.sub("", picks_blob)
    return [
        token.removeprefix("#")
        for token in ID_TOKEN_RE.findall(without_drought_refs)
    ]


def _previous_handoff_stamp(path: Path = HANDOFF) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    headings = [
        match.group("stamp")
        for line in text.splitlines()
        if (match := HANDOFF_HEADING_RE.match(line))
    ]
    if len(headings) < 2:
        return None
    return headings[1]


def _verify_autoissue_quota(added: str) -> int:
    issue_ids = _extract_picked_issue_ids(added)
    if not issue_ids:
        return _fail(
            "Could not extract the 30 picked AutoIssue IDs for the database check."
        )
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "backend",
        "python",
        "manage.py",
        "verify_autoissue_quota",
        "--ids",
        *issue_ids,
    ]
    previous_stamp = _previous_handoff_stamp()
    if previous_stamp:
        cmd.extend(["--resolved-after", previous_stamp])
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return _fail(
            "Docker is not available, so the AutoIssue database could not be checked. "
            "Start the backend stack and commit again."
        )
    except OSError as exc:
        return _fail(
            "The AutoIssue database check could not run. "
            f"System error: {exc}"
        )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        return _fail(
            "The handoff claims 30 AutoIssues, but the database check did not pass.\n"
            f"{detail}"
        )
    return 0


def _validate_ci_failed_runs(added: str) -> int:
    """Phase 7 — the third required marker (after HANDOFF READ + REGISTRY READ).

    Confirms the new AGENT-HANDOFF entry includes a
    `[CI FAILED RUNS READ: ...]` line proving the agent ran
    `gh run list --status failure --limit 10` (or recorded that `gh`
    was unavailable). The skipped form is accepted so contributors
    without `gh` aren't blocked, but it must still be PRESENT.
    """
    if CI_FAILED_RUNS_RE.search(added):
        return 0
    return _fail(
        "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
        "the `[CI FAILED RUNS READ: ...]` marker required by Phase 7 of the "
        "test-hardening plan.\n"
        "  Run `docker compose exec -T backend python manage.py print_open_issues` "
        "— it prints both required markers in one call.\n"
        "  If `gh` is unavailable on this machine, the printed form will be "
        "`[CI FAILED RUNS READ: skipped — gh unavailable]`, which the hook "
        "still accepts. Copy that line into the handoff."
    )


def _validate_guidelines_read(added: str) -> int:
    """FR-251 — the fourth required marker.

    Confirms the agent read both AI-CODING-GUIDELINES.md and
    docs/CODE-COVERAGE-RULES.md at session start. Exact format:
    `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]`.
    """
    if GUIDELINES_READ_RE.search(added):
        return 0
    return _fail(
        "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
        "the `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]` "
        "marker required by FR-251.\n"
        "  Read both files at session start; emit the marker as-is. The marker "
        "exists so every agent confirms it understands the per-task coverage "
        "targets in the guidelines before claiming any work is done."
    )


def _parse_quality_result(body: str) -> dict[str, str]:
    results: dict[str, str] = {}
    result_parts = re.findall(
        r"([a-z_]+)\s*=\s*([^=]+?)(?=\s+[a-z_]+\s*=|$)",
        body,
    )
    for key, value in result_parts:
        results[key.lower()] = value.strip().lower()
    return results


def _validate_quality_gate_for_code(added: str, staged_code_files: list[str]) -> int:
    if not staged_code_files:
        return 0
    listed = ", ".join(staged_code_files[:8])
    if len(staged_code_files) > 8:
        listed += f", and {len(staged_code_files) - 8} more"
    if not QUALITY_GATE_READ_RE.search(added):
        return _fail(
            "Code files are staged, but the handoff does not include the "
            "`[QUALITY GATE READ: ...]` marker. Add the marker after "
            "`[GUIDELINES READ: ...]` before committing. Staged code files: "
            f"{listed}"
        )
    result_match = QUALITY_GATE_RESULT_RE.search(added)
    if not result_match:
        return _fail(
            "Code files are staged, but the handoff does not include the "
            "`[QUALITY GATE RESULT: ...]` marker. Code commits must prove "
            "guidelines, tests, coverage, mutation tests, and check setup all "
            "passed before commit. Staged code files: "
            f"{listed}"
        )
    results = _parse_quality_result(result_match.group("body"))
    for key, expected in QUALITY_REQUIRED_RESULTS.items():
        actual = results.get(key)
        if actual != expected:
            return _fail(
                "Code files are staged, but the quality result is not passing. "
                f"Expected `{key}={expected}` and found `{key}={actual or 'missing'}`. "
                "Do not commit code with failing tests, unmet coverage, skipped "
                "mutation tests, missing tools, broken containers, unavailable "
                "checks, or known guideline violations. Fix the code or the "
                "check setup until every required value passes."
            )
    return 0


def _validate_self_review_for_code(added: str, staged_code_files: list[str]) -> int:
    if not staged_code_files:
        return 0
    match = SELF_REVIEW_RESULT_RE.search(added)
    if not match:
        return _fail(
            "Code files are staged, but the handoff does not include the "
            "`[SELF REVIEW RESULT: ...]` marker. Review the task scope, "
            "log real findings as AutoIssues, fix safe in-scope issues, and "
            "record the result before committing. This hard block means the "
            "agent must review its own code for bugs, silent errors, "
            "correctness, tech debt, maintainability, duplication, and long "
            "functions before commit."
        )
    results = _parse_quality_result(match.group("body"))
    missing = sorted(SELF_REVIEW_REQUIRED_KEYS - set(results))
    if missing:
        return _fail(
            "The self-review marker is missing required fields: "
            f"{', '.join(missing)}. Required fields are: "
            f"{', '.join(sorted(SELF_REVIEW_REQUIRED_KEYS))}."
        )
    if results["issues"] not in {"fixed-or-none", "fixed", "none", "logged"}:
        return _fail(
            "The self-review marker must say whether issues were fixed, "
            "logged, or not found. Use `issues=fixed-or-none`, `issues=fixed`, "
            "`issues=logged`, or `issues=none`."
        )
    return 0


def _validate_bdd_proof_for_code(added: str, staged_code_files: list[str]) -> int:
    if not staged_code_files:
        return 0
    match = BDD_PROOF_RE.search(added)
    if not match:
        return _fail(
            "Code files are staged, but the handoff does not include the "
            "`[BDD PROOF: ...]` marker. Claude and Codex must communicate "
            "plans and summaries in behavior terms before signing off."
        )
    body = match.group("body").lower()
    missing = [word for word in ("given", "when", "then") if word not in body]
    if missing:
        return _fail(
            "The BDD proof marker must include `Given`, `When`, and `Then`. "
            f"Missing: {', '.join(missing)}."
        )
    return 0


def _validate_tdd_proof_for_code(added: str, staged_code_files: list[str]) -> int:
    if not staged_code_files:
        return 0
    match = TDD_PROOF_RE.search(added)
    if not match:
        return _fail(
            "Code files are staged, but the handoff does not include the "
            "`[TDD PROOF: ...]` marker. Claude and Codex must write or update "
            "a focused test before or alongside code, run it, fix the code, "
            "and rerun until it passes."
        )
    results = _parse_quality_result(match.group("body"))
    missing = sorted({"before_or_alongside", "tests", "result"} - set(results))
    if missing:
        return _fail(
            "The TDD proof marker is missing required fields: "
            f"{', '.join(missing)}. Required fields are: "
            "`before_or_alongside`, `tests`, and `result`."
        )
    if results["before_or_alongside"] not in {"yes", "true", "passed"}:
        return _fail(
            "The TDD proof marker must show the test was written or updated "
            "before or alongside the code. Use `before_or_alongside=yes`."
        )
    if results["result"] != "passed":
        return _fail(
            "The TDD proof marker must show `result=passed`. Do not commit "
            "code while the focused TDD test is failing, skipped, or not run."
        )
    return 0


def _validate_lesson_read_for_code(added: str, staged_code_files: list[str]) -> int:
    if not staged_code_files:
        return 0
    if LESSON_READ_RE.search(added):
        return 0
    return _fail(
        "Code files are staged, but the handoff does not prove AutoIssue "
        "lesson reading. Before writing tests or code, run "
        "`manage.py search_resolved_issues --area <touched-path>` and record "
        "`[RESOLVED HISTORY: ...]` or `[AUTOISSUE LESSONS READ: ...]`."
    )


def _validate_coverage_gaps(added: str) -> int:
    """FR-251 — the fifth required marker.

    Confirms the agent picked 10 coverage-gap AutoIssues to drain this
    session (alongside the 30-pick auto-issues + 10 latest failed CI
    runs). Accepts the populated form, the drought form, and the
    `0 picked + 10 to file` form when the queue is empty.
    """
    if COVERAGE_GAPS_RE.search(added):
        return 0
    return _fail(
        "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
        "the `[COVERAGE GAPS READ: ...]` marker required by FR-251.\n"
        "  Run `docker compose exec -T backend python manage.py print_open_issues` "
        "— it now prints the coverage-gap marker alongside the auto-issue and "
        "CI-failure markers.\n"
        "  Drain rate: 10 coverage-gap AutoIssues per session. If fewer than 10 "
        "are open, the drought form `<K> picked + <10-K> to file — ...` is "
        "accepted and the agent files the remainder per docs/CODE-COVERAGE-RULES.md."
    )


def _validate_coverage_summary(added: str) -> int:
    """FR-251 strengthening (2026-05-12) — the sixth required marker.

    Confirms the new AGENT-HANDOFF entry includes a
    `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met]` line.
    Both target and actual MUST be percentages with the `%` symbol per
    the Plain-English Absolutism rule in `PLAIN-ENGLISH-RULE.md`.

    Documentation-only sessions use `target=0% actual=0% — met (no
    code changes; no coverage applicable)`.
    """
    if COVERAGE_SUMMARY_RE.search(added):
        return 0
    return _fail(
        "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
        "a valid `[COVERAGE SUMMARY: ...]` marker required by FR-251 (strengthened "
        "2026-05-12). Both `target=` and `actual=` MUST be percentages with the "
        "`%` symbol.\n"
        "  Bad:  [COVERAGE SUMMARY: target=Level A actual=8/8 tests — met]\n"
        "  Bad:  [COVERAGE SUMMARY: target=N/A actual=N/A — met]\n"
        "  Good: [COVERAGE SUMMARY: target=90% actual=92.5% — met]\n"
        "  Good: [COVERAGE SUMMARY: target=75% actual=68.0% — not met — reason]\n"
        "  Good (docs-only): [COVERAGE SUMMARY: target=0% actual=0% — met "
        "(no code changes; no coverage applicable)]\n"
        "  Run `docker compose exec -T backend python manage.py measure_coverage "
        "--module <path>` to capture the actual percentage for the files you touched."
    )


def _first_failure(validators: list[Callable[[], int]]) -> int:
    for validator in validators:
        if (rc := validator()) != 0:
            return rc
    return 0


def main() -> int:
    if (rc := _first_failure([
        _validate_no_unstaged_session_files,
        _validate_no_generated_build_files,
        _validate_no_temporary_test_artifacts,
    ])) != 0:
        return rc
    staged_files = _staged_files()
    staged_code_files = _staged_code_files()
    touches_handoff = _commit_touches_handoff()
    if staged_files and not touches_handoff:
        return _fail(
            "Staged files are present but `AGENT-HANDOFF.md` is not staged. "
            "Every commit must include the handoff entry with 30 picked "
            "AutoIssue IDs, the quota proof, and the required quality "
            "markers. Do not skip the AutoIssue quota, even for docs or "
            "tooling-only commits."
        )
    if not touches_handoff:
        return 0
    added = _staged_diff_for(HANDOFF)
    if (rc := _first_failure([
        lambda: _validate_marker(added),
        lambda: _validate_picks(added),
        lambda: _validate_ci_failed_runs(added),
        lambda: _validate_guidelines_read(added),
        lambda: _validate_quality_gate_for_code(added, staged_code_files),
        lambda: _validate_self_review_for_code(added, staged_code_files),
        lambda: _validate_bdd_proof_for_code(added, staged_code_files),
        lambda: _validate_tdd_proof_for_code(added, staged_code_files),
        lambda: _validate_lesson_read_for_code(added, staged_code_files),
        lambda: _validate_coverage_gaps(added),
        lambda: _validate_coverage_summary(added),
    ])) != 0:
        return rc
    return _verify_autoissue_quota(added)


if __name__ == "__main__":
    sys.exit(main())
