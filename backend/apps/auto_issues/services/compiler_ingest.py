"""File Rust compiler warnings as deduped AutoIssues.

Pure parsing lives in compiler_warnings.py; this layer turns each warning into
a deduped AutoIssue via the shared upsert_dedup, mirroring the pickers. Rust is
the only active compiled backend language.
"""

from __future__ import annotations

import hashlib

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.compiler_warnings import (
    CompilerWarning,
    parse_warnings,
)
from apps.auto_issues.services.dedup import upsert_dedup

# AutoIssue.external_id is CharField(max_length=128) and both fingerprint
# fields are CharField(max_length=64). Raw rust compiler keys routinely exceed
# those limits for real source paths, so we file a
# short readable external_id and a stable 16-char hex dedup key.
_EXTERNAL_ID_MAX = 128
_HASH_LEN = 16


def ingest_compiler_warnings(text: str, language: str, *, dry_run: bool = False) -> dict:
    """Parse `text` for `language` and file one deduped AutoIssue per warning."""
    warnings = parse_warnings(text, language)
    if dry_run:
        return {"parsed": len(warnings), "filed": 0}
    filed = sum(1 for warning in warnings if _file_warning(warning))
    return {"parsed": len(warnings), "filed": filed}


def _dedup_key(warning: CompilerWarning) -> str:
    """Readable (file, line, code-or-message) identity for one diagnostic."""
    tail = warning.code or warning.message[:48]
    return f"rust_compiler:{warning.language}:{warning.file}:{warning.line}:{tail}"


def _short_hash(key: str) -> str:
    """16-char hex digest that fits the 64-char fingerprint columns."""
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:_HASH_LEN]


def _external_id(key: str, fingerprint: str) -> str:
    """Readable id that stays unique even when the key is truncated.

    Short keys pass through verbatim. Long keys keep a readable head and append
    the hash so two diagnostics that share the first 128 chars never collide on
    the (source, external_id) database key.
    """
    if len(key) <= _EXTERNAL_ID_MAX:
        return key
    head = key[: _EXTERNAL_ID_MAX - _HASH_LEN - 1]
    return f"{head}:{fingerprint}"


def _file_warning(warning: CompilerWarning) -> bool:
    key = _dedup_key(warning)
    fingerprint = _short_hash(key)
    external_id = _external_id(key, fingerprint)
    is_error = warning.severity == "error"
    detail = warning.message or warning.code or "compiler diagnostic"
    location = f"{warning.file}:{warning.line}" + (f":{warning.col}" if warning.col else "")
    upsert_dedup(
        canonical=fingerprint,
        source=AutoIssue.SOURCE_RUST_COMPILER,
        external_id=external_id,
        fingerprint=fingerprint,
        title=f"[rust compiler] {warning.severity}: {detail}"[:200],
        description=(
            f"{location} {warning.severity}: {warning.message} "
            f"{f'[{warning.code}]' if warning.code else ''}".strip()
        ),
        affected_files=[warning.file],
        severity=AutoIssue.SEVERITY_HIGH if is_error else AutoIssue.SEVERITY_LOW,
        priority_score=0.7 if is_error else 0.35,
        occurrence_count=_next_occurrence_count(external_id),
        category_key="correctness",
    )
    return True


def _next_occurrence_count(external_id: str) -> int:
    existing = (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_RUST_COMPILER, external_id=external_id)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )
    return int(existing.occurrence_count or 0) + 1 if existing else 1
