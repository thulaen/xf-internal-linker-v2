"""Phase 4.9 — Compression Audit (read-only weekly scan).

Plain-English: walks a curated list of large per-row tables (JSONField
diagnostics blobs, BinaryField vectors, the SupersededEmbedding
archive), samples ~1000 rows per table, runs the bytes through zlib
compression, and reports the ratio + projected disk savings if the
operator chose to compress that column going forward.

The audit DOES NOT compress anything. It produces a "Top 10
compressible artefacts" report stored as a single AppSetting row that
the operator can review on the diagnostics page; the actual "apply
compression" + "rollback" path is a follow-up (Phase 4.9 sub-gaps 2
and 10).

Storage discipline:
    * ONE AppSetting row keyed ``compression_audit.last_report``
      carrying the JSON-encoded list. Update-not-append so storage
      stays bounded at 1 row total.
    * A second AppSetting row ``compression_audit.last_run_at``
      carries the ISO-8601 timestamp.

Compression choice: stdlib ``zlib`` at level 6. Python's stdlib has
no zstd built-in and adding ``zstandard`` would cost a Docker image
rebuild — not worth it for a read-only audit where the ratio is the
metric and zlib's ratio on text/JSON is within 10-15% of zstd's.
When the operator chooses to apply compression, the apply-path can
upgrade to zstd (which IS available via psycopg's TOAST hook).

Citations:
    * Postgres TOAST docs §70.2 — what's already auto-compressed
      (anything > 2 KB after row-pack).
    * Facebook zstd benchmark (2016) — ratios on text-like data.
    * RFC 1950 — zlib container format.
"""

from __future__ import annotations

import json
import logging
import zlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from django.utils import timezone

logger = logging.getLogger(__name__)


# Default sample size per table. 1000 rows is enough to estimate the
# compression ratio to within ~1% (sample-size law for compressible
# text); higher gains us very little but costs more I/O.
_DEFAULT_SAMPLE_SIZE = 1000

# zlib compression level. 6 is Python's default — good ratio without
# the ~3x slowdown of level 9. Used only for the audit; the
# apply-compression path (Phase 4.9 sub-gap 2) chooses its own level.
_AUDIT_COMPRESSION_LEVEL = 6

# Minimum projected savings (bytes) to include a candidate in the
# top-N report. Tables that would only save a few KB aren't worth
# the operator's time even if the ratio looks good.
_MIN_REPORTED_SAVINGS_BYTES = 1 * 1024 * 1024  # 1 MB

# AppSetting keys for the persisted single-row report + timestamp.
_KEY_REPORT = "compression_audit.last_report"
_KEY_RUN_AT = "compression_audit.last_run_at"


@dataclass(frozen=True, slots=True)
class CompressionCandidate:
    """One table+columns combination's audit verdict."""

    table_label: str
    model_dotted_name: str
    columns: tuple[str, ...]
    rows_sampled: int
    raw_bytes_per_row_avg: float
    compressed_bytes_per_row_avg: float
    compression_ratio: float  # compressed / raw  (lower is better)
    estimated_total_rows: int
    estimated_savings_bytes: int  # rows × (raw_avg − compressed_avg)
    notes: str = ""


@dataclass(frozen=True, slots=True)
class CompressionAuditReport:
    """Whole-run summary the operator sees on /diagnostics."""

    run_at_iso: str
    sample_size: int
    candidates: list[CompressionCandidate] = field(default_factory=list)
    total_estimated_savings_bytes: int = 0
    note: str = ""


# Curated list of (model dotted-name, columns, label, notes). Each
# entry is a known-large per-row payload that JSON-or-bytes could
# meaningfully compress. Keep this list short (~12 entries) so the
# audit run finishes in seconds, not minutes.
#
# Adding a new candidate: pick a model that actually has BinaryField
# OR JSONField with avg row > 1 KB. Confirm with `EXPLAIN (ANALYZE,
# BUFFERS) SELECT pg_column_size(<col>) FROM <table> LIMIT 100;` first.
_CANDIDATES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    # JSONField diagnostics blobs on ContentItem — typically 200-2000 bytes
    # each; tens of thousands of rows.
    (
        "apps.content.models.ContentItem",
        ("passages",),
        "ContentItem.passages JSON",
        "Passage list per content item — JSON of dicts.",
    ),
    (
        "apps.content.models.ContentItem",
        ("salient_entities",),
        "ContentItem.salient_entities JSON",
        "Per-item salient entity scores.",
    ),
    (
        "apps.content.models.ContentItem",
        ("engagement_quality_diagnostics",),
        "ContentItem.engagement_quality_diagnostics JSON",
        "Engagement quality breakdown.",
    ),
    (
        "apps.content.models.ContentItem",
        ("content_value_diagnostics",),
        "ContentItem.content_value_diagnostics JSON",
        "Content value breakdown.",
    ),
    (
        "apps.content.models.ContentItem",
        ("canonical_url_history",),
        "ContentItem.canonical_url_history JSON",
        "Per-item canonical-URL change log.",
    ),
    (
        "apps.content.models.ContentItem",
        ("nlp_metadata",),
        "ContentItem.nlp_metadata JSON",
        "Per-item NLP enrichment payload (lemmas, noun chunks, etc.).",
    ),
    (
        "apps.content.models.ContentItem",
        ("pipeline_diagnostics",),
        "ContentItem.pipeline_diagnostics JSON",
        "Per-item pipeline-stage diagnostics.",
    ),
    # AuditEvent + OperationEvent runtime_context — millions of rows
    # over time, even tiny per-row savings add up. Field names verified
    # 2026-05-04 against the live model schemas.
    (
        "apps.audit.models.AuditEvent",
        ("metadata",),
        "AuditEvent.metadata JSON",
        "Per-event metadata blob.",
    ),
    (
        "apps.ops_feed.models.OperationEvent",
        ("runtime_context",),
        "OperationEvent.runtime_context JSON",
        "Per-event runtime context.",
    ),
    # SupersededEmbedding archive — raw float32 vectors, very compressible.
    (
        "apps.content.models.SupersededEmbedding",
        ("embedding",),
        "SupersededEmbedding.embedding vector",
        "Archived float32 vectors awaiting prune.",
    ),
    # OPQ codebook — small but recurring binary blobs.
    (
        "apps.content.models.OPQCodebook",
        ("rotation", "codebooks"),
        "OPQCodebook.rotation+codebooks BinaryField",
        "Per-codebook rotation matrix + centroids.",
    ),
)


def run_compression_audit(
    *, sample_size: int = _DEFAULT_SAMPLE_SIZE
) -> CompressionAuditReport:
    """Run the audit and persist the report. Returns the report.

    Plain-English: walks every candidate table, samples up to
    ``sample_size`` rows, measures the compression ratio + projected
    savings, sorts by savings, and persists the top entries to a
    single AppSetting row that the operator-facing endpoint reads.
    """
    candidates: list[CompressionCandidate] = []
    for dotted_name, columns, label, notes in _CANDIDATES:
        candidate = _audit_one_table(
            dotted_name=dotted_name,
            columns=columns,
            label=label,
            notes=notes,
            sample_size=sample_size,
        )
        if candidate is not None:
            candidates.append(candidate)

    # Filter to material savings + sort by absolute savings descending.
    significant = [
        c
        for c in candidates
        if c.estimated_savings_bytes >= _MIN_REPORTED_SAVINGS_BYTES
    ]
    significant.sort(key=lambda c: c.estimated_savings_bytes, reverse=True)

    total_savings = sum(c.estimated_savings_bytes for c in significant)
    note = (
        f"Audited {len(_CANDIDATES)} candidate tables; "
        f"{len(significant)} have ≥{_MIN_REPORTED_SAVINGS_BYTES // (1024 * 1024)} MB "
        f"projected savings."
    )
    report = CompressionAuditReport(
        run_at_iso=timezone.now().isoformat(),
        sample_size=sample_size,
        candidates=significant[:10],  # Top 10 (per Phase 4.9 sub-gap 1)
        total_estimated_savings_bytes=total_savings,
        note=note,
    )
    _persist_report(report)
    return report


def get_last_compression_audit() -> CompressionAuditReport | None:
    """Read the persisted report. Returns None if no audit has run yet."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=_KEY_REPORT).first()
        if row is None or not row.value:
            return None
        payload = json.loads(row.value)
        candidates = [
            CompressionCandidate(
                table_label=c["table_label"],
                model_dotted_name=c["model_dotted_name"],
                columns=tuple(c["columns"]),
                rows_sampled=c["rows_sampled"],
                raw_bytes_per_row_avg=c["raw_bytes_per_row_avg"],
                compressed_bytes_per_row_avg=c["compressed_bytes_per_row_avg"],
                compression_ratio=c["compression_ratio"],
                estimated_total_rows=c["estimated_total_rows"],
                estimated_savings_bytes=c["estimated_savings_bytes"],
                notes=c.get("notes", ""),
            )
            for c in payload.get("candidates", [])
        ]
        return CompressionAuditReport(
            run_at_iso=payload.get("run_at_iso", ""),
            sample_size=int(payload.get("sample_size", _DEFAULT_SAMPLE_SIZE)),
            candidates=candidates,
            total_estimated_savings_bytes=int(
                payload.get("total_estimated_savings_bytes", 0)
            ),
            note=payload.get("note", ""),
        )
    except Exception:  # noqa: BLE001 — bad JSON or DB blip: treat as "no report yet".
        logger.debug("compression_audit: report read failed", exc_info=True)
        return None


# ── Internal helpers ─────────────────────────────────────────────


def _audit_one_table(
    *,
    dotted_name: str,
    columns: tuple[str, ...],
    label: str,
    notes: str,
    sample_size: int,
) -> CompressionCandidate | None:
    """Sample one table; return its candidate row or None on failure."""
    model_class = _import_model(dotted_name)
    if model_class is None:
        return None
    try:
        total_rows = model_class.objects.count()
    except Exception:  # noqa: BLE001 — model may exist but table not migrated yet on a fresh install.
        logger.debug(
            "compression_audit: count failed for %s", dotted_name, exc_info=True
        )
        return None
    if total_rows == 0:
        return None

    sample = _sample_and_measure(
        model_class, columns, n=min(sample_size, total_rows), dotted_name=dotted_name
    )
    if sample is None:
        return None
    raw_total, compressed_total, rows_seen = sample
    if rows_seen == 0 or raw_total == 0:
        return None

    raw_avg = raw_total / rows_seen
    compressed_avg = compressed_total / rows_seen
    return CompressionCandidate(
        table_label=label,
        model_dotted_name=dotted_name,
        columns=columns,
        rows_sampled=rows_seen,
        raw_bytes_per_row_avg=round(raw_avg, 1),
        compressed_bytes_per_row_avg=round(compressed_avg, 1),
        compression_ratio=round(compressed_avg / max(raw_avg, 1.0), 3),
        estimated_total_rows=total_rows,
        estimated_savings_bytes=int((raw_avg - compressed_avg) * total_rows),
        notes=notes,
    )


def _sample_and_measure(
    model_class,
    columns: tuple[str, ...],
    *,
    n: int,
    dotted_name: str,
) -> tuple[int, int, int] | None:
    """Stream up to ``n`` rows; return ``(raw_total, compressed_total, rows_seen)``.

    Returns ``None`` if the queryset iteration itself blew up so the
    caller can skip this candidate cleanly.
    """
    raw_total = 0
    compressed_total = 0
    rows_seen = 0
    try:
        for row in _sample_rows(model_class, columns, n):
            raw, compressed = _measure_row(row, columns)
            raw_total += raw
            compressed_total += compressed
            rows_seen += 1
    except Exception:  # noqa: BLE001 — table read failure is non-fatal; skip this candidate.
        logger.debug(
            "compression_audit: sample failed for %s", dotted_name, exc_info=True
        )
        return None
    return raw_total, compressed_total, rows_seen


def _import_model(dotted_name: str):
    """Import ``apps.x.models.ModelName`` or return None if missing."""
    try:
        module_path, _, class_name = dotted_name.rpartition(".")
        from importlib import import_module

        module = import_module(module_path)
        return getattr(module, class_name, None)
    except Exception:  # noqa: BLE001 — pre-Django-init / fresh install: model not importable yet.
        logger.debug(
            "compression_audit: model import failed for %s",
            dotted_name,
            exc_info=True,
        )
        return None


def _sample_rows(model_class, columns: tuple[str, ...], n: int) -> Iterable[dict]:
    """Yield up to ``n`` rows as ``{column: value}`` dicts.

    Uses ``.order_by("pk")`` + slice rather than ``.order_by("?")``
    because random-order on large tables forces a full sort. The
    first-N-by-PK sample is biased toward older rows but is fine for
    a compression-ratio estimate (compressibility doesn't drift much
    with row age on the audited columns).
    """
    return (
        model_class.objects.order_by("pk")
        .values(*columns)
        .iterator(chunk_size=min(n, 200))
    )


def _measure_row(row: dict, columns: tuple[str, ...]) -> tuple[int, int]:
    """Return ``(raw_bytes, compressed_bytes)`` for one row's columns."""
    chunks: list[bytes] = []
    for col in columns:
        value = row.get(col)
        chunks.append(_value_to_bytes(value))
    raw_bytes = b"".join(chunks)
    if not raw_bytes:
        return (0, 0)
    compressed = zlib.compress(raw_bytes, level=_AUDIT_COMPRESSION_LEVEL)
    return (len(raw_bytes), len(compressed))


def _value_to_bytes(value: Any) -> bytes:
    """Best-effort byte-encode of a column value. Defensive."""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace")
    if isinstance(value, (list, dict, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8", errors="replace"
            )
        except (TypeError, ValueError):
            return repr(value).encode("utf-8", errors="replace")
    # Numbers / dates / unknown: stringify
    return str(value).encode("utf-8", errors="replace")


def _persist_report(report: CompressionAuditReport) -> None:
    """Update the single-row AppSetting payload. Best-effort."""
    try:
        from apps.core.models import AppSetting

        # Convert to plain JSON-friendly dict (tuples → lists for columns).
        payload = asdict(report)
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        AppSetting.objects.update_or_create(
            key=_KEY_REPORT,
            defaults={"value": json.dumps(payload)},
        )
        AppSetting.objects.update_or_create(
            key=_KEY_RUN_AT,
            defaults={"value": report.run_at_iso},
        )
    except Exception:  # noqa: BLE001 — persistence is best-effort; next run will retry.
        logger.debug("compression_audit: persist failed", exc_info=True)
