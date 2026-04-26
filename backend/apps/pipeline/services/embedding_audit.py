"""Fortnightly embedding-accuracy scan (plan Part 3, FR-231).

Read-only classifier. Categorises every ContentItem embedding into one of:

    ok               — present, correct dim, correct signature, norm in band, resample agrees
    null             — no embedding; content exists but vector is NULL
    wrong_dim        — vector length does not match the current provider
    wrong_signature  — embedding_model_version does not match current signature
    drift_norm       — L2 norm outside [1 - tol, 1 + tol]; storage corruption
    drift_resample   — random sample re-embedded with current provider; cosine < threshold

Returns an ``AuditReport`` + a list of flagged PKs the task should pass to
``generate_all_embeddings(pks, force_reembed=False)``. The existing signature
filter inside that function ensures zero-duplicate writes.

Performance:
  * Streams ``iterator(chunk_size=500)`` over rows so peak memory stays tiny.
  * ``np.linalg.norm`` on batches of 500 = O(dim) per row; <10 ms per chunk.
  * Resample set drawn once per run, not per item.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuditReport:
    total: int = 0
    ok: int = 0
    null: int = 0
    wrong_dim: int = 0
    wrong_signature: int = 0
    drift_norm: int = 0
    drift_resample: int = 0
    flagged_pks: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "total": self.total,
            "ok": self.ok,
            "null": self.null,
            "wrong_dim": self.wrong_dim,
            "wrong_signature": self.wrong_signature,
            "drift_norm": self.drift_norm,
            "drift_resample": self.drift_resample,
            "flagged": len(self.flagged_pks),
        }


def scan_embedding_health(
    *,
    current_signature: str,
    current_dimension: int,
    norm_tolerance: float = 0.02,
    drift_threshold: float = 0.9999,
    resample_size: int = 50,
) -> AuditReport:
    """Scan every active ContentItem and classify its embedding state."""
    from apps.content.models import ContentItem

    report = AuditReport()
    qs = ContentItem.objects.filter(is_deleted=False).values_list(
        "pk", "embedding", "embedding_model_version"
    )

    # First pass: classify. Second pass (resample) below uses a sub-sample.
    candidates_for_resample: list[int] = []
    for pk, emb, sig in qs.iterator(chunk_size=500):
        report.total += 1
        if emb is None:
            report.null += 1
            report.flagged_pks.append(pk)
            continue
        try:
            vec = np.asarray(emb, dtype=np.float32)
        except Exception:
            report.wrong_dim += 1
            report.flagged_pks.append(pk)
            continue
        if vec.shape[0] != current_dimension:
            report.wrong_dim += 1
            report.flagged_pks.append(pk)
            continue
        if sig != current_signature:
            report.wrong_signature += 1
            report.flagged_pks.append(pk)
            continue
        norm = float(np.linalg.norm(vec))
        if abs(norm - 1.0) > norm_tolerance:
            report.drift_norm += 1
            report.flagged_pks.append(pk)
            continue
        candidates_for_resample.append(pk)

    # Pick a random subset for the resample check. The rest stay ``ok``.
    ok_count = len(candidates_for_resample)
    if ok_count <= resample_size:
        sample_pks = candidates_for_resample
    else:
        rng = random.Random(42)
        sample_pks = rng.sample(candidates_for_resample, resample_size)

    resample_flagged = _resample_check(
        pks=sample_pks,
        current_dimension=current_dimension,
        drift_threshold=drift_threshold,
    )
    report.drift_resample = len(resample_flagged)
    for pk in resample_flagged:
        report.flagged_pks.append(pk)
    # Everything that stayed in the resample pool and passed is ``ok``.
    report.ok = ok_count - len(resample_flagged)
    return report


def _resample_check(
    *,
    pks: list[int],
    current_dimension: int,
    drift_threshold: float,
) -> list[int]:
    """Re-embed each pk with the current provider, compare cosine to stored vec."""
    if not pks:
        return []
    try:
        from apps.content.models import ContentItem
        from apps.pipeline.services.embedding_providers import get_provider
    except Exception:
        return []

    rows = {
        row["pk"]: row
        for row in ContentItem.objects.filter(pk__in=pks).values(
            "pk", "embedding", "title", "distilled_text"
        )
    }

    try:
        provider = get_provider()
    except Exception:
        return []

    flagged: list[int] = []
    for pk in pks:
        row = rows.get(pk)
        if row is None:
            continue
        stored = row.get("embedding")
        if stored is None:
            continue
        try:
            stored_vec = np.asarray(stored, dtype=np.float32)
        except Exception:
            continue
        if stored_vec.shape[0] != current_dimension:
            continue
        text = f"{row.get('title') or ''}\n\n{row.get('distilled_text') or ''}".strip()
        if not text:
            continue
        try:
            new_vec = provider.embed_single(text)
        except Exception as exc:
            logger.debug("resample embed failed pk=%s: %s", pk, exc)
            continue
        if new_vec.shape[0] != stored_vec.shape[0]:
            flagged.append(pk)
            continue
        cos = float(np.dot(stored_vec, new_vec))
        if cos < drift_threshold:
            flagged.append(pk)
    return flagged


# ---------------------------------------------------------------------------
# Fortnight-gate helpers
# ---------------------------------------------------------------------------


def is_audit_enabled() -> bool:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key="embedding.accuracy_check_enabled").first()
        if row and str(row.value).lower() in ("false", "0", "no", "off"):
            return False
    except Exception:
        pass
    return True


def get_last_run_at():
    try:
        from apps.core.models import AppSetting
        from django.utils.dateparse import parse_datetime

        row = AppSetting.objects.filter(key="embedding.accuracy_last_run_at").first()
        if row and row.value:
            return parse_datetime(str(row.value))
    except Exception:
        pass
    return None


def set_last_run_at(dt) -> None:
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="embedding.accuracy_last_run_at",
            defaults={"value": dt.isoformat()},
        )
    except Exception:
        logger.debug("set_last_run_at failed", exc_info=True)


def get_thresholds() -> tuple[float, float, int]:
    """Return ``(norm_tolerance, drift_threshold, resample_size)``."""

    def _f(key: str, fallback: float) -> float:
        try:
            from apps.core.models import AppSetting

            row = AppSetting.objects.filter(key=key).first()
            if row and row.value not in (None, ""):
                return float(row.value)
        except Exception:
            pass
        return fallback

    def _i(key: str, fallback: int) -> int:
        try:
            from apps.core.models import AppSetting

            row = AppSetting.objects.filter(key=key).first()
            if row and row.value not in (None, ""):
                return int(row.value)
        except Exception:
            pass
        return fallback

    return (
        _f("embedding.audit_norm_tolerance", 0.02),
        _f("embedding.audit_drift_threshold", 0.9999),
        _i("embedding.audit_resample_size", 50),
    )


def write_diagnostic(*, run_id: str | None, report: AuditReport) -> None:
    """Persist the audit summary as a PipelineDiagnostic row for the explorer."""
    try:
        from apps.suggestions.models import PipelineDiagnostic

        PipelineDiagnostic.objects.create(
            pipeline_run_id=run_id,
            destination_content_item_id=0,
            destination_content_type="audit",
            skip_reason="embedding_audit",
            details=json.dumps(report.as_dict()),
        )
    except Exception:
        logger.debug("PipelineDiagnostic write failed for audit", exc_info=True)


__all__ = [
    "AuditReport",
    "get_last_run_at",
    "get_thresholds",
    "is_audit_enabled",
    "scan_embedding_health",
    "set_last_run_at",
    "write_diagnostic",
]
