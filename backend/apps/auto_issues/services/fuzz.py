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
        # Still emit coverage-gap rows even when no crashes exist —
        # those don't depend on the crashes dir.
        return pick_fuzz_coverage_gaps()

    count = 0
    for entry in crashes_dir.iterdir():
        if not entry.is_file():
            continue
        kind = _kind_from_filename(entry.name)
        if not kind:
            continue
        if _upsert_crash(entry, kind):
            count += 1
    # Always also emit / refresh coverage-gap rows on the same beat.
    count += pick_fuzz_coverage_gaps()
    logger.info("fuzz picker: landed %d AutoIssue rows", count)
    return count


def pick_fuzz_coverage_gaps() -> int:
    """Emit `kind=fuzz-coverage-gap` AutoIssue rows for C++ source files
    without a matching `fuzz_<name>.cpp` target.

    Phase 6 follow-up of the test-hardening plan (landed under FR-251).
    The libFuzzer ratchet: every public C++ hot-path module should have
    a fuzz target. Files surfaced here are added to the ratchet by the
    standard 18-pick / 10-coverage drain.

    Heuristic: enumerate `backend/extensions/*.cpp` (top-level only,
    skipping `tests/`, `benchmarks/`, `build*/`, `fuzz/`). For each,
    check whether `backend/extensions/fuzz/fuzz_<name>.cpp` exists.
    If not, file an AutoIssue.

    The function is best-effort. When the extensions dir isn't
    reachable (test environments), it logs and returns 0.
    """
    ext_root = _resolve("backend/extensions")
    if not ext_root.is_dir():
        # Try the docker container read-only mount.
        ext_root = Path("/repo/backend/extensions")
        if not ext_root.is_dir():
            logger.info("fuzz coverage-gap: backend/extensions/ not found; skipping")
            return 0

    fuzz_dir = ext_root / "fuzz"
    existing_fuzz_targets: set[str] = set()
    if fuzz_dir.is_dir():
        for entry in fuzz_dir.iterdir():
            name = entry.name
            if name.startswith("fuzz_") and name.endswith(".cpp"):
                existing_fuzz_targets.add(name[len("fuzz_") : -len(".cpp")])

    severity = _appsetting("fuzz.coverage_gap_severity", AutoIssue.SEVERITY_LOW)

    count = 0
    for src in sorted(ext_root.iterdir()):
        if not src.is_file() or src.suffix != ".cpp":
            continue
        stem = src.stem
        # Skip non-public / utility files. The convention is that
        # public hot-path modules sit at the top level of extensions/;
        # tests/benchmarks/build* are filtered by being subdirectories.
        if stem in existing_fuzz_targets:
            continue
        # Don't gap-flag the fuzz targets themselves or the test files
        # that may have leaked into the top level.
        if stem.startswith(("test_", "fuzz_", "bench_")):
            continue
        if _upsert_coverage_gap(stem, src):
            count += 1
    if count:
        logger.info("fuzz coverage-gap picker: emitted %d gap rows", count)
    return count


def _upsert_coverage_gap(module_stem: str, src_path: Path) -> bool:
    """File one `kind=fuzz-coverage-gap` AutoIssue for a missing target."""
    title = f"[fuzz-coverage-gap] {module_stem}.cpp has no fuzz target"
    culprit = f"fuzz-coverage-gap:{module_stem}"
    fp = canonical_fingerprint(title, culprit)
    description = (
        f"`backend/extensions/{module_stem}.cpp` has no matching "
        f"`backend/extensions/fuzz/fuzz_{module_stem}.cpp` target.\n\n"
        f"The libFuzzer ratchet expects one fuzz target per public C++ "
        f"hot-path module. See `backend/extensions/fuzz/AUTHORING.md` "
        f"for the per-target template.\n\n"
        f"Fix shape: add `fuzz/fuzz_{module_stem}.cpp` invoking the "
        f"module's public entry point with the libFuzzer byte-stream "
        f"interface; register it in `backend/extensions/fuzz/CMakeLists.txt`; "
        f"add a 60-second smoke step to the `cpp-libfuzzer-smoke` CI job."
    )
    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_FUZZ,
            "kind": "fuzz-coverage-gap",
            "fingerprint": fp,
            "severity": AutoIssue.SEVERITY_LOW,
            "tool": "libfuzzer-ratchet",
        },
    ):
        try:
            upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_FUZZ,
                external_id=f"coverage-gap:{module_stem}",
                fingerprint=fp,
                title=title[:512],
                description=description,
                affected_files=[f"backend/extensions/{module_stem}.cpp"],
                severity=AutoIssue.SEVERITY_LOW,
                priority_score=0.3,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001
            logger.exception("fuzz coverage-gap: upsert failed for %s", module_stem)
            return False
    return True


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
