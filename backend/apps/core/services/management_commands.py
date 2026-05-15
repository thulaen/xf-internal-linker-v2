"""Helpers for Django management-command startup decisions."""

from __future__ import annotations

from pathlib import PurePath

LIGHTWEIGHT_MANAGEMENT_COMMANDS = frozenset(
    {
        "auto_issues_append_registry",
        "backfill_canonical_fingerprint",
        "ingest_quality_evidence",
        "log_self_review_issue",
        "measure_coverage",
        "print_open_issues",
        "print_resolved_issues",
        "prune_quality_artifacts",
        "resolve_autoissue",
        "search_resolved_issues",
        "verify_autoissue_quota",
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
