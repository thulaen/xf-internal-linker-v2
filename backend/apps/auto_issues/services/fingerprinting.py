"""Cross-source canonical fingerprinting.

Each source (GlitchTip, internal `ingest_error`, Pyroscope) computes its
own per-source fingerprint that won't naturally collide with the others.
This module provides a SINGLE source-agnostic hash so the same root cause
captured by multiple sources lands on ONE `AutoIssue` row instead of
piling up.

Algorithm: lower-case the title + culprit, normalise digit runs and
filesystem paths to placeholders, sha1, take 16 hex chars. Same shape
as `apps.audit.error_ingest._compute_fingerprint` but without the
job_type/step prefix (which is internal-source-specific).
"""

from __future__ import annotations

import hashlib
import re

# Same normalisers as `apps.audit.error_ingest._normalise` so an internal
# error and a GlitchTip event with the same exception message hash to
# the same canonical fingerprint.
_DIGIT_RUN = re.compile(r"\d{2,}")
_PATH = re.compile(r"/[^\s'\"]+")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def _normalise(text: str) -> str:
    """Strip the variable parts so the same root cause hashes consistently."""
    if not text:
        return ""
    out = text.strip().lower()
    out = _UUID.sub("<uuid>", out)
    out = _HEX.sub("<hex>", out)
    out = _PATH.sub("<path>", out)
    out = _DIGIT_RUN.sub("<n>", out)
    return out


def _path_title_fingerprint(file: str, title: str) -> str:
    """Exact lesson fingerprint that preserves directory boundaries."""
    path = file.replace("\\", "/").strip("/").lower()
    normalized_title = title.strip().lower()
    key = f"{path}::{normalized_title}"
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def canonical_fingerprint(
    title: str | None = None,
    culprit: str | None = None,
    *,
    file: str | None = None,
) -> str:
    """Source-agnostic 16-char hex fingerprint.

    Same value across sources for the same root cause. Two distinct root
    causes with the same title hash to the same value (lossy by design —
    the title IS the operator-visible identity of the bug).

    When `file` is supplied, the helper switches to the path-title lesson
    contract: slash direction is normalized, but directory boundaries are
    preserved so unrelated TDD lessons cannot collapse into one row.
    """
    if file is not None:
        if not file.strip() or not (title or "").strip():
            raise ValueError("file and title are required for path-title fingerprinting")
        return _path_title_fingerprint(file, title or "")
    culprit_text = "" if culprit is None else culprit
    title_text = "" if title is None else title
    norm = f"{_normalise(title_text)}|{_normalise(culprit_text)}"
    return hashlib.sha1(norm.encode(), usedforsecurity=False).hexdigest()[:16]
