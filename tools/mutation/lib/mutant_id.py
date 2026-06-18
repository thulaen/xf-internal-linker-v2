"""Stable mutant identifiers for distributed mutation reports."""

from __future__ import annotations

import hashlib


def mutant_id(tool: str, file_path: str, line: int, description: str) -> str:
    """Return a short stable fingerprint for one mutant."""
    normalized_path = file_path.replace("\\", "/")
    raw = f"{tool}|{normalized_path}|{line}|{description}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]
