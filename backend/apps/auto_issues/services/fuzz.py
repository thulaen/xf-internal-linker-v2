"""libFuzzer crash + coverage-gap picker — Phase 6 of the test-hardening plan.

Scans `backend/extensions/fuzz/` for `crash-<sha1>`, `oom-<sha1>`,
`leak-<sha1>`, `timeout-<sha1>` reproducer files dropped by libFuzzer
on a crashing or memory-leaking input. Each unique reproducer becomes
one AutoIssue with `source='fuzz'`, `kind='crash'` (or oom/leak/timeout).

Also emits `kind='fuzz-coverage-gap'` rows for every public C++ API in
`backend/extensions/*.cpp` without a matching `fuzz/fuzz_*.cpp` target
— the libFuzzer ratchet. As fuzz targets are added per the AutoIssue
queue, these gap rows resolve.

Initial implementation: scans the crashes directory only. Coverage-gap
detection lands in a follow-up PR once we have a stable list of public
C++ entry points to scan against.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from opentelemetry import trace

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

_CRASH_PREFIXES = ("crash-", "oom-", "leak-", "timeout-")


def _appsetting(key: str, default: str) -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row and row.value:
            return str(row.value)
    except Exception:  # noqa: BLE001
        pass
    return default


def _resolve(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    base = getattr(settings, "BASE_DIR", Path.cwd())
    return Path(base) / p


def pick_fuzz_crashes() -> int:
    """Scan the crashes dir and upsert each reproducer. Returns row count."""
    crashes_dir = _resolve(_appsetting("fuzz.crashes_dir", "backend/extensions/fuzz"))
    if not crashes_dir.is_dir():
        logger.info("fuzz picker: %s is not a directory; skipping", crashes_dir)
        return 0

    count = 0
    for entry in crashes_dir.iterdir():
        if not entry.is_file():
            continue
        kind = _kind_from_filename(entry.name)
        if not kind:
            continue
        if _upsert_crash(entry, kind):
            count += 1
    logger.info("fuzz picker: landed %d AutoIssue rows", count)
    return count


def _kind_from_filename(name: str) -> str:
    for prefix in _CRASH_PREFIXES:
        if name.startswith(prefix):
            return prefix.rstrip("-")
    return ""


def _upsert_crash(path: Path, kind: str) -> bool:
    sha = path.name.split("-", 1)[1] if "-" in path.name else path.name
    title = f"[fuzz-{kind}] {sha}"
    culprit = f"fuzz:{path.name}"
    fp = canonical_fingerprint(title, culprit)
    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_FUZZ,
            "kind": kind,
            "fingerprint": fp,
            "severity": AutoIssue.SEVERITY_HIGH,
            "tool": "libfuzzer",
        },
    ):
        try:
            upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_FUZZ,
                external_id=sha,
                fingerprint=fp,
                title=title,
                description=f"libFuzzer reproducer at {path}",
                affected_files=[str(path.relative_to(_resolve(".")))],
                severity=AutoIssue.SEVERITY_HIGH,
                priority_score=0.85,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001
            logger.exception("fuzz picker: upsert failed for %s", path.name)
            return False
    return True
