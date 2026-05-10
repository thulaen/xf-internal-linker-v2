#!/usr/bin/env python3
"""Pre-commit guard for the auto-fix-12-issues rule (raised 2026-05-10).

When an AGENT-HANDOFF.md entry is added or edited in this commit, the new
content MUST include the `[REGISTRY READ: ...]` marker proving the agent
read the open auto-issues list at session-start.

The marker has TWO halves:

1. **Per-source breakdown.** Format:
   `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / <p> pyroscope / <l> loki), <M> registry`
   The four per-source numbers must sum to <N>.

2. **Picks.** Format:
   `picked: #<id1>, #<id2>, #<id3>, #<id4> | gp: #<id5>, #<id6>, #<id7>, #<id8> | l: #<id9>, #<id10>, #<id11>, #<id12>]`
   Exactly 12 ID tokens (matching `#\\S+`) total. The drought-substitution
   form `l: 0 found + 4 from agent: #..., #..., #..., #... (drought logged: #...)`
   is also accepted, provided `drought logged: #<id>` is present and the
   total ID count still reaches 12.

A `satisfier` exemption phrase (`auto-fix-12 satisfier` or
`auto-fix-3 satisfier` for backwards compat) replaces the picks half when
the session's own user-task is itself a multi-bug fix that satisfies the
quota structurally — for example, this very rule-update session.

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

# The marker header — captures the per-source breakdown numbers so we
# can assert they sum to N.
NEW_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*(?P<n>\d+)\s+open\s*"
    r"\(\s*(?P<a>\d+)\s+agent\s*/\s*"
    r"(?P<g>\d+)\s+glitchtip\s*/\s*"
    r"(?P<p>\d+)\s+pyroscope\s*/\s*"
    r"(?P<l>\d+)\s+loki\s*\)",
    re.IGNORECASE,
)
# Backwards-compatible legacy header (old 3-pick rule). We REJECT this
# format on a fresh commit but report a helpful message that points at
# the new one. Same regex as the legacy hook.
LEGACY_MARKER_RE = re.compile(
    r"\[REGISTRY READ:\s*\d+\s+open auto-issues",
    re.IGNORECASE,
)
# Inside the picks half, count IDs of the form #<token>. We require 12.
ID_TOKEN_RE = re.compile(r"#[A-Za-z0-9._-]+")
# Satisfier exemption — covers legacy "auto-fix-3 satisfier" and the
# new "auto-fix-12 satisfier".
SATISFIER_RE = re.compile(r"auto-fix-(?:3|12)\s+satisfier", re.IGNORECASE)
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
    """Return the staged additions for *path* (lines starting with '+ ')."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0", "--", rel],
            cwd=REPO_ROOT,
            text=True,
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
        if LEGACY_MARKER_RE.search(added):
            return _fail(
                "Found the legacy 3-pick `[REGISTRY READ: <N> open auto-issues, ...]` "
                "marker. The rule was raised to 12 picks per session on 2026-05-10 "
                "(plan does-adding-qodana-make-swift-wall.md Stream 5).\n"
                "  Expected: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / "
                "<p> pyroscope / <l> loki), <M> registry — picked: #..., #..., #..., "
                "#... | gp: #..., #..., #..., #... | l: #..., #..., #..., #...]`\n"
                "  Run `docker compose exec -T backend python manage.py print_open_issues` "
                "to get the per-source counts, pick 12 issues (4 + 4 GlitchTip/Pyroscope "
                "+ 4 Loki), and rewrite the marker."
            )
        return _fail(
            "This commit modifies AGENT-HANDOFF.md but the new lines do not contain "
            "any `[REGISTRY READ: ...]` marker. The ABSOLUTE rule in CLAUDE.md / "
            "AGENTS.md requires running `manage.py print_open_issues` at session "
            "start and recording the result.\n"
            "  Expected format: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip "
            "/ <p> pyroscope / <l> loki), <M> registry — picked: #..., ...]`"
        )
    a = int(new_match.group("a"))
    g = int(new_match.group("g"))
    p = int(new_match.group("p"))
    l = int(new_match.group("l"))
    n = int(new_match.group("n"))
    if a + g + p + l != n:
        return _fail(
            f"Per-source counts in `[REGISTRY READ: ...]` do not sum to N: "
            f"{a} agent + {g} glitchtip + {p} pyroscope + {l} loki = "
            f"{a + g + p + l}, but the header says {n} open. Re-run "
            "`print_open_issues --source <each>` and reconcile."
        )
    return 0


def _validate_picks(added: str) -> int:
    if SATISFIER_RE.search(added):
        return 0  # satisfier exemption — session task is the multi-fix itself
    picks_match = PICKS_SEGMENT_RE.search(added)
    if not picks_match:
        return _fail(
            "The `[REGISTRY READ: ...]` marker is present but does not include a "
            "`picked: #..., #..., ...]` segment. Need 12 picks total (4 + 4 "
            "GlitchTip/Pyroscope + 4 Loki) OR the `auto-fix-12 satisfier` phrase."
        )
    picks_blob = picks_match.group("picks")
    ids = ID_TOKEN_RE.findall(picks_blob)
    # Drought-substitution form may include the drought-AutoIssue id; we
    # don't require it to count toward 12, but we DO require the phrase.
    has_drought_phrase = bool(DROUGHT_PHRASE_RE.search(picks_blob))
    drought_id_count = len(DROUGHT_PHRASE_RE.findall(picks_blob))
    has_substitution_form = bool(re.search(r"\bfrom\s+agent\b", picks_blob, re.IGNORECASE))
    effective_picks = len(ids) - drought_id_count
    if effective_picks != 12:
        return _fail(
            f"Expected exactly 12 picked issue IDs in the `picked: ...` segment "
            f"(4 + 4 GlitchTip/Pyroscope + 4 Loki). Found {effective_picks} "
            f"(raw # tokens = {len(ids)}, drought log refs = {drought_id_count}).\n"
            "  If a category was empty at session-start, use the substitution "
            "form: `l: 0 found + 4 from agent: #..., #..., #..., #... "
            "(drought logged: #<id>)` — and file an `AutoIssue(kind='picker_drought')` "
            "for that source so the next agent investigates."
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
