"""Helpers for Django management-command startup decisions."""

from __future__ import annotations

from pathlib import PurePath

LIGHTWEIGHT_MANAGEMENT_COMMANDS = frozenset(
    {
        "auto_issues_append_registry",
        "backfill_canonical_fingerprint",
        "ingest_quality_evidence",
        "log_code_review_lessons",
        "log_self_review_issue",
        "repair_restored_backup_schema",
        "report_hook_false_positive",
        "measure_coverage",
        "print_open_issues",
        "print_resolved_issues",
        "prune_quality_artifacts",
        "resolve_autoissue",
        "search_resolved_issues",
        "verify_autoissue_quota",
        # Day-3 paper-trail / lesson-index commands.
        "record_perf_baseline",
        "verify_perf_speedup",
        "log_performance_exemption",
        "cite_spec",
        "read_scoped_lessons",
        "verify_tdd_cycle",
        "verify_spec_citation",
        "prune_test_artefacts",
        # Existing paper-trail commands.
        "defer_work",
        "resolve_paper_trail",
        "print_open_paper_trail",
        "verify_paper_trail_quota",
        "search_paper_trail",
        "migrate_handoff_deferrals",
        # New status helpers (2026-05-16).
        "mark_paper_trail_stale",
        "link_paper_trail_supersedes",
    }
)


def is_lightweight_management_command(argv: list[str] | tuple[str, ...]) -> bool:
    """Return True when a command only needs models and should skip startup work."""
    return any(
        _normalise_command_name(arg) in LIGHTWEIGHT_MANAGEMENT_COMMANDS
        for arg in argv[1:]
        if not arg.startswith("-")
    )


def _normalise_command_name(arg: str) -> str:
    command = PurePath(arg).name
    return command.removesuffix(".exe").removesuffix(".py")
