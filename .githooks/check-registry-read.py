#!/usr/bin/env python3
"""Pre-commit guard for the auto-fix-18-issues rule (raised 2026-05-11).

When an AGENT-HANDOFF.md entry is added or edited in this commit, the new
content MUST include the `[REGISTRY READ: ...]` marker proving the agent
read the open auto-issues list at session-start.

The marker has TWO halves:

1. **Per-source breakdown.** Format:
   `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / <p> pyroscope / <t> tempo / <l> loki / <f> faro), <M> registry`
   The six per-source numbers must sum to <N>.

2. **Picks.** Format:
   `picked: #<id1>, #<id2>, #<id3> | g: #<id4>, #<id5>, #<id6> | p: #<id7>, #<id8>, #<id9> | t: #<id10>, #<id11>, #<id12> | l: #<id13>, #<id14>, #<id15> | f: #<id16>, #<id17>, #<id18>]`
   Exactly 18 ID tokens (matching `#\\S+`) total — 3 per source × 6 sources.
   The drought-substitution form `t: 0 found + 3 from agent: #..., #..., #... (drought logged: #...)`
   is accepted per-bucket, provided `drought logged: #<id>` is present and
   the total ID count still reaches 18.

A `satisfier` exemption phrase (`auto-fix-18 satisfier` or the legacy
`auto-fix-12 satisfier` / `auto-fix-3 satisfier`) replaces the picks half
when the session's own user-task is itself a multi-bug fix that satisfies
the quota structurally — for example, the very session that lifted the
rule from 12 to 18.

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

# The marker header — captures the six per-source breakdown numbers so
# we can assert they sum to N.  Order: agent / glitchtip / pyroscope /
# tempo / loki / faro (the 6-source ritual raised on 2026-05-11).
NEW_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*(?P<n>\d+)\s+open\s*"
    r"\(\s*(?P<a>\d+)\s+agent\s*/\s*"
    r"(?P<g>\d+)\s+glitchtip\s*/\s*"
    r"(?P<p>\d+)\s+pyroscope\s*/\s*"
    r"(?P<t>\d+)\s+tempo\s*/\s*"
    r"(?P<l>\d+)\s+loki\s*/\s*"
    r"(?P<f>\d+)\s+faro\s*\)",
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
# Inside the picks half, count IDs of the form #<token>. We require 18.
ID_TOKEN_RE = re.compile(r"#[A-Za-z0-9._-]+")
# Satisfier exemption — covers the new "auto-fix-18 satisfier" plus the
# legacy "auto-fix-12" and "auto-fix-3" phrases.
SATISFIER_RE = re.compile(r"auto-fix-(?:3|12|18)\s+satisfier", re.IGNORECASE)
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


def _validate_marker(added: str) -> int:
    new_match = NEW_MARKER_RE.search(added)
    if not new_match:
        if FOUR_SOURCE_MARKER_RE.search(added):
            return _fail(
                "Found the 4-source / 12-pick `[REGISTRY READ: <N> open "
                "(<a> agent / <g> glitchtip / <p> pyroscope / <l> loki), ...]` "
                "marker. The rule was raised to 18 picks across 6 sources on "
                "2026-05-11 (plan objective-deploy-and-integrate-zany-bee.md "
                "Stream 8).\n"
                "  Expected: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / "
                "<p> pyroscope / <t> tempo / <l> loki / <f> faro), <M> registry — "
                "picked: #..., #..., #... | g: #..., #..., #... | p: #..., #..., #... "
                "| t: #..., #..., #... | l: #..., #..., #... | f: #..., #..., #...]`\n"
                "  Run `docker compose exec -T backend python manage.py print_open_issues "
                "--source <each>` for the six per-source counts (agent, glitchtip, "
                "pyroscope, tempo, loki, faro), pick 18 issues (3 per source), and "
                "rewrite the marker."
            )
        if LEGACY_MARKER_RE.search(added):
            return _fail(
                "Found the pre-2026-05-10 legacy `[REGISTRY READ: <N> open auto-issues, "
                "...]` marker. The rule has been raised twice since then (12 picks on "
                "2026-05-10, 18 picks on 2026-05-11).\n"
                "  Expected: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / "
                "<p> pyroscope / <t> tempo / <l> loki / <f> faro), <M> registry — "
                "picked: #...x3 | g: #...x3 | p: #...x3 | t: #...x3 | l: #...x3 | f: #...x3]`."
            )
        return _fail(
            "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
            "any `[REGISTRY READ: ...]` marker. The ABSOLUTE rule in CLAUDE.md / "
            "AGENTS.md requires running `manage.py print_open_issues` at session "
            "start and recording the result.\n"
            "  Expected format: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip "
            "/ <p> pyroscope / <t> tempo / <l> loki / <f> faro), <M> registry — picked: #..., ...]`"
        )
    a = int(new_match.group("a"))
    g = int(new_match.group("g"))
    p = int(new_match.group("p"))
    t = int(new_match.group("t"))
    l = int(new_match.group("l"))
    f = int(new_match.group("f"))
    n = int(new_match.group("n"))
    total = a + g + p + t + l + f
    if total != n:
        return _fail(
            f"Per-source counts in `[REGISTRY READ: ...]` do not sum to N: "
            f"{a} agent + {g} glitchtip + {p} pyroscope + {t} tempo + "
            f"{l} loki + {f} faro = {total}, but the header says {n} open. "
            "Re-run `print_open_issues --source <each>` and reconcile."
        )
    return 0


def _validate_picks(added: str) -> int:
    if SATISFIER_RE.search(added):
        return 0  # satisfier exemption — session task is the multi-fix itself
    picks_match = PICKS_SEGMENT_RE.search(added)
    if not picks_match:
        return _fail(
            "The `[REGISTRY READ: ...]` marker is present but does not include a "
            "`picked: #..., ...]` segment. Need 18 picks total (3 from each of "
            "agent, glitchtip, pyroscope, tempo, loki, faro) OR the "
            "`auto-fix-18 satisfier` phrase."
        )
    picks_blob = picks_match.group("picks")
    ids = ID_TOKEN_RE.findall(picks_blob)
    # Drought-substitution form may include the drought-AutoIssue id; we
    # don't require it to count toward 18, but we DO require the phrase.
    has_drought_phrase = bool(DROUGHT_PHRASE_RE.search(picks_blob))
    drought_id_count = len(DROUGHT_PHRASE_RE.findall(picks_blob))
    has_substitution_form = bool(re.search(r"\bfrom\s+agent\b", picks_blob, re.IGNORECASE))
    effective_picks = len(ids) - drought_id_count
    if effective_picks != 18:
        return _fail(
            f"Expected exactly 18 picked issue IDs in the `picked: ...` segment "
            f"(3 per source × 6 sources). Found {effective_picks} "
            f"(raw # tokens = {len(ids)}, drought log refs = {drought_id_count}).\n"
            "  If a per-source bucket was empty at session-start, use the "
            "substitution form: `t: 0 found + 3 from agent: #..., #..., #... "
            "(drought logged: #<id>)` — and file an "
            "`AutoIssue(kind='picker_drought')` for that source so the next agent "
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


def main() -> int:
    if not _commit_touches_handoff():
        return 0
    added = _staged_diff_for(HANDOFF)
    if (rc := _validate_marker(added)) != 0:
        return rc
    return _validate_picks(added)


if __name__ == "__main__":
    sys.exit(main())
