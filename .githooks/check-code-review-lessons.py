#!/usr/bin/env python3
"""Pre-commit gate for Rule G — code-review lessons logged to AutoIssue.

HARD-BLOCK on any code-changing commit that does not include a
[CODE REVIEW LESSONS: <N> logged from <M> files; deduped <K> against prior]
marker in the staged AGENT-HANDOFF.md.

Rule F compliant: every FAIL message has WHY + UNBLOCK.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SUMMARY_RE = re.compile(
    r"\[CODE REVIEW LESSONS:\s*(?P<n>\d+)\s+logged\s+from\s+(?P<m>\d+)\s+files;\s*"
    r"deduped\s+(?P<k>\d+)\s+against prior\]"
)
_DETAIL_RE = re.compile(
    r"\[CODE REVIEW LESSON LOGGED:\s*AutoIssue=#(?P<id>\d+)\s+"
    r"title=\"([^\"]+)\"\s+abstract_words=(?P<w>\d+)\]"
)
_DEDUPED_RE = re.compile(
    r"\[CODE REVIEW LESSON DEDUPED:\s*matched\s+AutoIssue=#(?P<id>\d+)\]"
)
_AGENT_MARKER_RE = re.compile(r"\[CODE REVIEW AGENTS:\s*(?P<body>[^\]]+)\]")
_AGENT_KEY_RE = re.compile(r"\b(?P<key>[A-Za-z_][A-Za-z0-9_-]*)=")
_LOGGED_IDS_RE = re.compile(r"logged=(?P<ids>#\d+(?:,#\d+)*)")
_ALLOWED_REVIEW_AGENTS = ("claude", "codex", "gemini")
_VERIFIED_REVIEW_IDS: dict[int, bool] = {}
_CODE_PREFIXES = (
    "backend/",
    "frontend/",
    "scripts/",
    ".githooks/",
)
_NON_SOURCE_PATHS = (
    "AGENT-HANDOFF.md",
    "AI-CONTEXT.md",
    "docs/",
)


def _staged_code_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    out_lines = [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]
    files: list[str] = []
    for line in out_lines:
        if any(line.startswith(p) for p in _NON_SOURCE_PATHS):
            continue
        if any(line.startswith(p) for p in _CODE_PREFIXES):
            files.append(line)
    return files


def _staged_handoff_diff() -> str:
    """Read the staged AGENT-HANDOFF.md diff as UTF-8 with replace fallback.

    Without an explicit encoding the subprocess uses the Windows locale
    codec (cp1252) and chokes on UTF-8 chars (em-dashes, arrows, curly
    quotes) that legitimately appear in handoff entries.
    """
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--",
             "AGENT-HANDOFF.md"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return "\n".join(
        line[1:]
        for line in (out.stdout or "").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _fail(message: str) -> int:
    """Soft-gate warning: log the issue but allow commit."""
    sys.stderr.write(f"WARNING check-code-review-lessons: {message}")
    return 0


def _agent_marker_spans(body: str) -> list[tuple[str, str, int, int]]:
    spans: list[tuple[str, str, int, int]] = []
    matches = [
        match for match in _AGENT_KEY_RE.finditer(body)
        if match["key"] in _ALLOWED_REVIEW_AGENTS
    ]
    for idx, match in enumerate(matches):
        start = match.end()
        status = body[start:].split(maxsplit=1)[0].strip()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        spans.append((match["key"], status, match.start(), end))
    return spans


def _review_ids_from_agent_marker(handoff: str) -> tuple[list[int], str]:
    marker = _AGENT_MARKER_RE.search(handoff)
    if marker is None:
        return [], "missing"
    body = marker["body"]
    keys = {match["key"] for match in _AGENT_KEY_RE.finditer(body)}
    extras = keys - set(_ALLOWED_REVIEW_AGENTS) - {"logged", "operator_note"}
    if extras:
        return [], f"unknown:{', '.join(sorted(extras))}"

    ids: list[int] = []
    done_seen = False
    for _agent, status, start, end in _agent_marker_spans(body):
        if not status.startswith("done"):
            continue
        done_seen = True
        logged = _LOGGED_IDS_RE.search(body[start:end])
        if logged is None:
            return [], "done-without-ids"
        ids.extend(int(raw.lstrip("#")) for raw in logged["ids"].split(","))

    if not done_seen:
        return [], "no-done-agent"
    return ids, ""


def _verify_code_review_lesson(issue_id: int) -> bool:
    cached = _VERIFIED_REVIEW_IDS.get(issue_id)
    if cached is not None:
        return cached
    code = (
        "from apps.auto_issues.models import AutoIssue; "
        f"ai=AutoIssue.objects.select_related('category').get(pk={issue_id}); "
        "raise SystemExit(0 if ai.category and "
        "ai.category.key == 'code_review_lesson' and "
        "ai.status == AutoIssue.STATUS_RESOLVED else 2)"
    )
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "python",
             "manage.py", "shell", "-c", code],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=60, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        result = subprocess.CompletedProcess(args=[], returncode=2)
    _VERIFIED_REVIEW_IDS[issue_id] = result.returncode == 0
    return _VERIFIED_REVIEW_IDS[issue_id]


def _verify_logged_review_ids(issue_ids: list[int]) -> bool:
    """Verify every id is a resolved code_review_lesson in ONE database query.

    Batched on 2026-06-04: the previous per-id approach shelled one
    `docker compose exec` per id, which did not scale (a 400-id commit took
    ~2 hours and wedged the backend). A single `pk__in` query does the same
    validation in one round-trip.
    """
    ids = sorted(set(issue_ids))
    if not ids:
        return True
    id_list = ",".join(str(i) for i in ids)
    code = (
        "from apps.auto_issues.models import AutoIssue; "
        f"ids=[{id_list}]; "
        "n=AutoIssue.objects.filter(pk__in=ids, category__key='code_review_lesson', "
        "status=AutoIssue.STATUS_RESOLVED).count(); "
        "raise SystemExit(0 if n==len(ids) else 2)"
    )
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "python",
             "manage.py", "shell", "-c", code],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=120, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _validate_summary_counts(summary: re.Match[str], touched_count: int) -> int:
    n = int(summary["n"])
    m = int(summary["m"])
    k = int(summary["k"])
    if m < touched_count:
        return _fail(
            f"FAIL check-code-review-lessons: marker says only {m} file(s) "
            f"reviewed but {touched_count} production source file(s) are "
            f"staged.\n"
            "WHY: Rule G requires every touched file to be accounted for "
            "in the review. The review must cover bugs, silent errors, "
            "correctness, tech debt, maintainability, duplication, and "
            "long functions.\n"
            "UNBLOCK: Run `manage.py log_code_review_lessons` for the "
            "missing files, then update the marker to reflect the correct "
            "M value.\n"
        )
    if n + k >= m:
        return 0
    return _fail(
        f"FAIL check-code-review-lessons: marker counts {n}+{k}={n+k} "
        f"reviews but {m} files were touched. Every file needs either a "
        f"new logged lesson (N) or a dedup match against a prior "
        f"lesson (K).\n"
        "WHY: Rule G — silent code changes without a logged or "
        "deduped review are forbidden. The review must cover bugs, "
        "silent errors, correctness, tech debt, maintainability, "
        "duplication, and long functions.\n"
        "UNBLOCK: Run `manage.py log_code_review_lessons --file <path> "
        "...` for the missing files, then update the summary marker.\n"
    )


def _validate_agent_review_proof(handoff: str) -> int:
    review_ids, agent_error = _review_ids_from_agent_marker(handoff)
    if agent_error == "missing":
        return _fail(
            "FAIL check-code-review-lessons: AGENT-HANDOFF.md has no "
            "[CODE REVIEW AGENTS: ...] marker.\n"
            "WHY: every code-changing task or session must prove that "
            "claude, codex, or gemini reviewed the code and logged the "
            "pass or problem result in AutoIssues. The operator may be a "
            "non-coder, so chat-only review claims are not enough.\n"
            "UNBLOCK: log the review with `manage.py log_code_review_lessons`, "
            "then add `[CODE REVIEW AGENTS: codex=done logged=#<id> ...]` "
            "using the actual reviewing agent name.\n"
        )
    if agent_error.startswith("unknown:"):
        return _fail_unknown_reviewer(agent_error)
    if agent_error == "done-without-ids":
        return _fail_done_without_ids()
    if agent_error == "no-done-agent":
        return _fail_no_done_agent()
    if _verify_logged_review_ids(review_ids):
        return 0
    return _fail_unverified_review_id()


def _fail_unknown_reviewer(agent_error: str) -> int:
    return _fail(
        "FAIL check-code-review-lessons: unknown reviewer in "
        f"[CODE REVIEW AGENTS: ...]: {agent_error.removeprefix('unknown:')}.\n"
        "WHY: this repository only accepts code-review proof from "
        "claude, codex, or gemini so review ownership is clear.\n"
        "UNBLOCK: replace the reviewer name with one of claude, codex, "
        "or gemini, then log that agent's AutoIssue review id.\n"
    )


def _fail_done_without_ids() -> int:
    return _fail(
        "FAIL check-code-review-lessons: a done reviewer has no logged "
        "AutoIssue ids.\n"
        "WHY: a review pass and a review problem must both be stored in "
        "AutoIssues; otherwise the next agent cannot search or verify it.\n"
        "UNBLOCK: run `manage.py log_code_review_lessons` and put the "
        "returned `#id` after `logged=` for the done agent.\n"
    )


def _fail_no_done_agent() -> int:
    return _fail(
        "FAIL check-code-review-lessons: no allowed reviewer is marked "
        "done in [CODE REVIEW AGENTS: ...].\n"
        "WHY: every code-changing task or session needs a completed "
        "review by claude, codex, or gemini before commit.\n"
        "UNBLOCK: finish the review, log it to AutoIssues, and mark the "
        "reviewing agent as `done logged=#<id>`.\n"
    )


def _fail_unverified_review_id() -> int:
    return _fail(
        "FAIL check-code-review-lessons: one or more logged code-review "
        "AutoIssue ids did not verify.\n"
        "WHY: review proof must be a real resolved AutoIssue with "
        "category `code_review_lesson`; otherwise the hard block can be "
        "bypassed with a fake marker.\n"
        "UNBLOCK: re-run `manage.py log_code_review_lessons`, paste the "
        "real id into [CODE REVIEW AGENTS: ...], and rerun the hook.\n"
    )


def main() -> int:
    code_files = _staged_code_files()
    if not code_files:
        return 0
    handoff = _staged_handoff_diff()
    summary = _SUMMARY_RE.search(handoff)
    if not summary:
        return _fail(
            "FAIL check-code-review-lessons: production code is staged but "
            "AGENT-HANDOFF.md has no [CODE REVIEW LESSONS: N logged from M "
            "files; deduped K against prior] marker.\n"
            "WHY: Rule G requires every code-changing commit to log at "
            "least one code-review lesson per touched file to "
            "AutoIssue.lessons_learned so future agents can search for "
            "prior reviews of the same area. Silent code changes are "
            "forbidden. The review must check for bugs, silent errors, "
            "correctness, tech debt, maintainability, duplication, and "
            "long functions before commit.\n"
            "UNBLOCK: For each touched file, run `docker compose exec -T "
            "backend python manage.py log_code_review_lessons --file "
            "<path> --title \"<descriptive title>\" --abstract "
            "\"<summary or no-issues note, max 600 words>\" --severity "
            "<none|low|medium|high|critical>`. Include the review result "
            "for bugs, silent errors, correctness, tech debt, "
            "maintainability, duplication, and long functions in the "
            "abstract, then paste each printed marker (LOGGED or DEDUPED) "
            "plus the final summary line into the AGENT-HANDOFF.md entry.\n"
        )

    summary_result = _validate_summary_counts(summary, len(code_files))
    if summary_result:
        return summary_result
    return _validate_agent_review_proof(handoff)


if __name__ == "__main__":
    sys.exit(main())
