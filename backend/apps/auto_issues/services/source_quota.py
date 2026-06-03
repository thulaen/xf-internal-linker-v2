"""Shared open-AutoIssue quota verification keyed by ``source``.

Several commit gates ask the same question: "are there unresolved
AutoIssues for one observability source, and is that count over a
ceiling?" CodeQL was the first such gate, but it keys off ``concept_tags``
because CodeQL findings predate the dedicated source constant. Every
source that DOES have a first-class ``AutoIssue.source`` value (GWP-ASan,
Perfetto, Loki, ...) can share one verified code path instead of cloning
the quota/block logic per source.

This keeps the language-ownership boundary clean: the quota *decision*
(how many open issues are allowed) is plain orchestration and stays in
Python; it is not a domain invariant that belongs in Haskell.
"""

from __future__ import annotations

from apps.auto_issues.models import AutoIssue


def open_issues_for_source(source: str):
    """Return unresolved AutoIssues for one ``source``, oldest first."""
    return (
        AutoIssue.objects.filter(source=source)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .order_by("first_seen", "id")
    )


def verify_source_quota(
    *, source: str, label: str, max_open: int, block_open: bool
) -> list[AutoIssue]:
    """Return open issues for ``source`` or raise when the commit must stop.

    Raises ``ValueError`` with a plain-English message when the open count
    exceeds ``max_open`` or when ``block_open`` is set and any remain open.
    """
    open_issues = list(open_issues_for_source(source))
    if len(open_issues) > max_open:
        raise ValueError(_quota_message(label, open_issues, max_open))
    if block_open and open_issues:
        raise ValueError(_block_message(label, open_issues))
    return open_issues


def _ids(issues: list[AutoIssue], limit: int = 11) -> str:
    return ", ".join(f"#{issue.pk}" for issue in issues[:limit])


def _quota_message(label: str, issues: list[AutoIssue], max_open: int) -> str:
    return (
        f"{label} has {len(issues)} open AutoIssues, above the maximum "
        f"{max_open}: {_ids(issues)}"
    )


def _block_message(label: str, issues: list[AutoIssue]) -> str:
    return (
        f"Unresolved {label} AutoIssues must be fixed or reviewed before "
        f"commit: {_ids(issues)}"
    )
