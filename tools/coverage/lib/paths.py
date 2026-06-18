"""Path normalization helpers for coverage adapters."""

from __future__ import annotations


def repo_path(path: str) -> str:
    """Normalize a path to repo-style forward slashes."""
    normalized = path.replace("\\", "/").strip()
    return normalized[2:] if normalized.startswith("./") else normalized
