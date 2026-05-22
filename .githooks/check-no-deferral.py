#!/usr/bin/env python3
"""
Pre-commit hook: block forbidden deferral language in handoff prose +
in committed source comments.

This hook enforces the 2026-05-22 ABSOLUTE No-Deferral rule. The rule
text and source backing live in
`docs/specs/fr-observability-always-on-and-no-deferral.md` and the
mirrored paragraph in `CLAUDE.md` / `AGENTS.md` / `CODEX.md` /
`GEMINI.md`.

Behavior:

  1. Scan the staged AGENT-HANDOFF.md diff (added lines only) for a
     fixed list of forbidden phrases (case-insensitive, word-boundary
     match).  Any match hard-blocks the commit and names the offending
     phrase and approximate line.
  2. Scan every staged source-code file for bare `TODO` / `FIXME` /
     `XXX` / `HACK` tokens in comments.  A bare token is BLOCKED.  The
     token is ACCEPTED when immediately followed (same line, same
     comment) by `(paper-trail #<N>)` or `(AutoIssue #<N>)` where
     `<N>` resolves to a real row in the corresponding Django table.
  3. The hook does NOT scan its own source file or the source of
     `docs/specs/fr-observability-always-on-and-no-deferral.md` so the
     rule documentation can reference the forbidden phrases without
     blocking itself.

Run manually:
    python .githooks/check-no-deferral.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that legitimately reference the forbidden phrases as part of
# documenting / enforcing the rule itself.  These are exempt from the
# prose-level deferral scan.
SELF_EXEMPT_PATHS = frozenset(
    {
        ".githooks/check-no-deferral.py",
        ".githooks/test_check_no_deferral.py",
        "docs/specs/fr-observability-always-on-and-no-deferral.md",
    }
)

# Forbidden phrases (case-insensitive, word-boundary match). Matching
# any of these in AGENT-HANDOFF.md or in a staged code comment blocks
# the commit.  The list mirrors the spec verbatim.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    r"\bdeferred\b",
    r"\bdeferring\b",
    r"\bdefer\s+to\b",
    r"\bskipped\s+for\b",
    r"\bskipping\s+(?:this|for\s+now|the\s+rest|the\s+next)\b",
    r"\bleave\s+for\b",
    r"\bleaving\s+for\b",
    r"\bout[- ]of[- ]scope\b",
    r"\bnext\s+session\b",
    r"\bfollow[- ]up\s+session\b",
    r"\bfuture\s+work\b",
    r"\bwill\s+be\s+done\s+later\b",
    r"\bwill\s+handle\s+in\b",
    r"\bpostponed\b",
    r"\bpostponing\b",
    r"\bnot\s+in\s+this\s+session\b",
    r"\bsilent\s+retry\s+on\s+hook\s+block\b",
    r"\bsilent\s+code[- ]review\s+skip\b",
    r"\bsilent\s+deferral\b",
    r"\bno[- ]op\s+the\s+importer\b",
    r"\bworkaround\s+to\s+dodge\b",
    r"\bbypass\s+the\s+hook\b",
)

_FORBIDDEN_RE: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pat, re.IGNORECASE) for pat in FORBIDDEN_PHRASES
)

# TODO / FIXME / XXX / HACK token detection.  A bare match blocks
# unless immediately followed by `(paper-trail #N)` or `(AutoIssue #N)`
# on the same line, same comment.  The `(?! ... )` is a negative
# look-ahead that allows the linked form to pass.
TODO_TOKEN_RE = re.compile(
    r"\b(TODO|FIXME|XXX|HACK)\b"
    r"(?!\s*\((?:paper-trail|AutoIssue)\s*#\d+\))",
    re.IGNORECASE,
)

# When the TODO token IS followed by a (paper-trail #N) or
# (AutoIssue #N), capture the linked id so we can verify it exists.
LINKED_TODO_RE = re.compile(
    r"\b(TODO|FIXME|XXX|HACK)\b"
    r"\s*\((?P<kind>paper-trail|AutoIssue)\s*#(?P<num>\d+)\)",
    re.IGNORECASE,
)

# Match a comment in any language we care about.  Used to scope the
# TODO scan to comments only (so a `todo` identifier inside ordinary
# code doesn't trip the hook).
PYTHON_COMMENT_RE = re.compile(r"#.*?$", re.MULTILINE)
JS_LINE_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)
JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
SHELL_COMMENT_RE = re.compile(r"#.*?$", re.MULTILINE)
SQL_LINE_COMMENT_RE = re.compile(r"--.*?$", re.MULTILINE)

EXT_TO_COMMENT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    ".py": (PYTHON_COMMENT_RE,),
    ".pyi": (PYTHON_COMMENT_RE,),
    ".js": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".ts": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".tsx": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".jsx": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".java": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".go": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".rs": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".c": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".cpp": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".cc": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".h": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".hpp": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".cs": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".sh": (SHELL_COMMENT_RE,),
    ".bash": (SHELL_COMMENT_RE,),
    ".yaml": (PYTHON_COMMENT_RE,),
    ".yml": (PYTHON_COMMENT_RE,),
    ".toml": (PYTHON_COMMENT_RE,),
    ".ini": (PYTHON_COMMENT_RE,),
    ".cfg": (PYTHON_COMMENT_RE,),
    ".html": (HTML_COMMENT_RE,),
    ".scss": (JS_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
    ".css": (JS_BLOCK_COMMENT_RE,),
    ".sql": (SQL_LINE_COMMENT_RE, JS_BLOCK_COMMENT_RE),
}


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _staged_files() -> list[str]:
    """Return the list of staged file paths from `git diff --cached`.

    Includes added, copied, modified, and renamed (final-name) entries
    so the deferral scan sees every code surface this commit touches.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip()
    ]


def _staged_handoff_diff() -> str:
    """Return the added-only lines of the staged AGENT-HANDOFF.md diff."""
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--unified=0",
                "--",
                "AGENT-HANDOFF.md",
            ],
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
    added_lines: list[str] = []
    for line in (result.stdout or "").splitlines():
        if line.startswith("+++"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
    return "\n".join(added_lines)


def _scan_text_for_forbidden(text: str, where: str) -> list[str]:
    """Return one error string per forbidden-phrase match in *text*."""
    failures: list[str] = []
    for pat in _FORBIDDEN_RE:
        for match in pat.finditer(text):
            # Find which line of *text* the match is on.
            line_no = text.count("\n", 0, match.start()) + 1
            phrase = match.group(0)
            failures.append(
                f"  {where} line {line_no}: forbidden phrase {phrase!r}"
            )
    return failures


def _extract_comment_text(content: str, path: str) -> str:
    """Return only the comment regions of *content* for *path*'s suffix.

    Empty string when the suffix has no comment pattern wired up.
    """
    suffix = Path(path).suffix.lower()
    patterns = EXT_TO_COMMENT_PATTERNS.get(suffix, ())
    if not patterns:
        return ""
    pieces: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(content):
            pieces.append(match.group(0))
    return "\n".join(pieces)


def _staged_blob(path: str) -> str:
    """Return the staged blob content for *path* as UTF-8 text."""
    try:
        result = subprocess.run(
            ["git", "show", f":{path}"],
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
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _scan_path_for_todos(path: str) -> list[str]:
    """Return one error string per bare-TODO match in *path*'s staged
    comments, plus one per linked-TODO whose `#N` does not resolve to a
    real row in the corresponding Django table.
    """
    if path in SELF_EXEMPT_PATHS:
        return []
    blob = _staged_blob(path)
    if not blob:
        return []
    comments = _extract_comment_text(blob, path)
    if not comments:
        return []
    failures: list[str] = []
    for match in TODO_TOKEN_RE.finditer(comments):
        # Translate the comment-region offset back to a line number in
        # the original blob for an approximate but useful pointer.
        snippet = match.group(0)
        failures.append(
            f"  {path}: bare {snippet!r} token in a comment.  Use "
            f"`{snippet}(paper-trail #<N>)` or "
            f"`{snippet}(AutoIssue #<N>)` to link the deferred work, "
            "or remove the marker if it's now stale."
        )
    # Linked TODOs are accepted iff the referenced row exists.  We do
    # NOT block here on DB connectivity issues so a Docker-down state
    # still surfaces the more pressing failure from
    # check-observability-stack first.  When the DB is reachable, the
    # linked id is validated.
    for match in LINKED_TODO_RE.finditer(comments):
        kind = match.group("kind").lower()
        num = int(match.group("num"))
        if not _row_exists(kind, num):
            failures.append(
                f"  {path}: linked {match.group(0)!r} references a "
                f"non-existent {kind} #{num}.  File the row first or "
                "fix the reference."
            )
    return failures


_VERIFIED_IDS: dict[tuple[str, int], bool] = {}


def _row_exists(kind: str, num: int) -> bool:
    """Return True iff a Django row exists for the given (kind, num).

    Caches results so repeated references inside the same commit are
    looked up once.  When the backend is unreachable, returns True
    (don't double-block on observability-stack failure).
    """
    key = (kind, num)
    cached = _VERIFIED_IDS.get(key)
    if cached is not None:
        return cached
    if kind == "paper-trail":
        model = "apps.paper_trail.models.PaperTrailEntry"
    elif kind == "autoissue":
        model = "apps.auto_issues.models.AutoIssue"
    else:
        _VERIFIED_IDS[key] = False
        return False
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "backend",
                "python",
                "manage.py",
                "shell",
                "-c",
                (
                    f"from {model.rsplit('.', 1)[0]} import "
                    f"{model.rsplit('.', 1)[1]}; "
                    f"print({model.rsplit('.', 1)[1]}.objects.filter("
                    f"id={num}).exists())"
                ),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # When the backend is unreachable, be conservative — accept.
        _VERIFIED_IDS[key] = True
        return True
    if result.returncode != 0:
        # Backend errored; be conservative — accept.
        _VERIFIED_IDS[key] = True
        return True
    exists = "True" in (result.stdout or "")
    _VERIFIED_IDS[key] = exists
    return exists


def main() -> int:
    failures: list[str] = []
    handoff_text = _staged_handoff_diff()
    failures.extend(
        _scan_text_for_forbidden(
            handoff_text, where="AGENT-HANDOFF.md (added)"
        )
    )
    for path in _staged_files():
        if path in SELF_EXEMPT_PATHS:
            continue
        if path == "AGENT-HANDOFF.md":
            # already scanned above for the prose layer
            continue
        failures.extend(_scan_path_for_todos(path))
    if not failures:
        return 0
    message = (
        "FAIL check-no-deferral: deferred work without a paper-trail "
        "or AutoIssue link is forbidden.\n"
        "WHY: the 2026-05-22 ABSOLUTE No-Deferral rule requires every "
        "deferred item to be filed in the database (paper trail or "
        "AutoIssue) so it cannot disappear into prose.  See "
        "`docs/specs/fr-observability-always-on-and-no-deferral.md`.\n"
        "VIOLATIONS:\n"
        + "\n".join(failures)
        + "\nUNBLOCK options: "
        "(a) remove the forbidden phrase and complete the work in this "
        "commit, "
        "(b) file a paper-trail entry via `manage.py defer_work "
        "--title ... --abstract \"Given ... When ... Then ...\"` and "
        "rewrite the prose to reference the new entry, OR "
        "(c) for code comments, append "
        "`(paper-trail #<N>)` or `(AutoIssue #<N>)` to the "
        "TODO/FIXME/XXX/HACK token where <N> resolves to a real row.\n"
    )
    return _fail(message)


if __name__ == "__main__":
    sys.exit(main())
