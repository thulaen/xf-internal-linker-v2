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


def canonical_fingerprint(title: str, culprit: str | None = None) -> str:
    """Source-agnostic 16-char hex fingerprint.

    Same value across sources for the same root cause. Two distinct root
    causes with the same title hash to the same value (lossy by design —
    the title IS the operator-visible identity of the bug).
    """
    culprit_text = "" if culprit is None else culprit
    norm = f"{_normalise(title)}|{_normalise(culprit_text)}"
    return hashlib.sha1(norm.encode()).hexdigest()[:16]
