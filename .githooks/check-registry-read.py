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

Bypass (intentional, e.g. mechanical merge): commit with --no-verify
ONLY if you explain in chat why. The hook has no allowlist.

Run manually:
    python .githooks/check-registry-read.py [path/to/AGENT-HANDOFF.md]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF = REPO_ROOT / "AGENT-HANDOFF.md"

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
# but report a helpful message pointing at the new 6-source form.
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


def _fail(msg: str) -> int:
    sys.stderr.write(f"\n\033[31m[check-registry-read]\033[0m FAIL: {msg}\n")
    return 1


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
    l = int(new_match.group("l"))
    f = int(new_match.group("f"))
    m = int(new_match.group("m"))
    z = int(new_match.group("z"))
    c = int(new_match.group("c"))
    gh = int(new_match.group("gh"))
    n = int(new_match.group("n"))
    total = a + g + p + t + l + f + m + z + c + gh
    if total != n:
        return _fail(
            f"Per-source counts in `[REGISTRY READ: ...]` do not sum to N: "
            f"{a} agent + {g} glitchtip + {p} pyroscope + {t} tempo + "
            f"{l} loki + {f} faro + {m} mutation + {z} fuzz + {c} contract + "
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
    ids = ID_TOKEN_RE.findall(picks_blob)
    # Drought-substitution form may include the drought-AutoIssue id; we
    # don't require it to count toward 30, but we DO require the phrase.
    has_drought_phrase = bool(DROUGHT_PHRASE_RE.search(picks_blob))
    drought_id_count = len(DROUGHT_PHRASE_RE.findall(picks_blob))
    has_substitution_form = bool(re.search(r"\bfrom\s+agent\b", picks_blob, re.IGNORECASE))
    effective_picks = len(ids) - drought_id_count
    if effective_picks != 30:
        return _fail(
            f"Expected exactly 30 picked issue IDs in the `picked: ...` segment "
            f"(3 per source × 10 sources). Found {effective_picks} "
            f"(raw # tokens = {len(ids)}, drought log refs = {drought_id_count}).\n"
            "  If a per-source bucket was empty at session-start, use the "
            "substitution form: `m: 0 found + 3 from agent: #..., #..., #... "
            "(drought logged: #<id>)` — and file an "
            "`AutoIssue(kind='picker_drought', source='agent')` for that source so the next agent "
            "investigates."
        )
    if has_substitution_form and not has_drought_phrase:
        return _fail(
            "Substitution form `+ K from agent:` is present but the required "
            "`(drought logged: #<id>)` phrase is missing. File an "
            "`AutoIssue(kind='picker_drought', source='agent')` for the dry "
            "source and reference its id in the marker."
        )
    return 0


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


def main() -> int:
    if not _commit_touches_handoff():
        return 0
    added = _staged_diff_for(HANDOFF)
    if (rc := _validate_marker(added)) != 0:
        return rc
    if (rc := _validate_picks(added)) != 0:
        return rc
    if (rc := _validate_ci_failed_runs(added)) != 0:
        return rc
    if (rc := _validate_guidelines_read(added)) != 0:
        return rc
    if (rc := _validate_coverage_gaps(added)) != 0:
        return rc
    if (rc := _validate_coverage_summary(added)) != 0:
        return rc
    return _verify_autoissue_quota(added)


if __name__ == "__main__":
    sys.exit(main())
