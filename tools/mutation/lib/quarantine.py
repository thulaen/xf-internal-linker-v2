"""Quarantine helpers for mutation run failures."""

from __future__ import annotations


def should_quarantine(status: str) -> bool:
    """Return true when a tool failure needs infrastructure follow-up."""
    return status in {"timeout", "oom", "tool_crash", "run_failure"}
