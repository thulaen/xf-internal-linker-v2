"""Shared mutation report schema helpers."""

from __future__ import annotations


def mutation_summary(tool: str, killed: int, survived: int, errors: int = 0) -> dict[str, object]:
    """Return one normalized mutation summary."""
    total = killed + survived
    score = 1.0 if total == 0 else killed / total
    if errors:
        status = "run_failure"
    elif survived:
        status = "survivor"
    else:
        status = "passed"
    return {
        "tool": tool,
        "killed": killed,
        "survived": survived,
        "errors": errors,
        "score": round(score, 4),
        "status": status,
    }
