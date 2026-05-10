"""Startup smoke checks for artifact-table discipline."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable

from django.apps import apps
from django.db import models

logger = logging.getLogger(__name__)

WARNING_TEMPLATE = (
    "New table {table_name} added without no-dups invariant. "
    "See NO-DUPLICATES.md to fix."
)


@dataclass(frozen=True)
class ArtifactRule:
    model_label: str
    dedupe_fields: tuple[str, ...]
    retention_field: str | None = None
    supersede_field: str | None = None


ARTIFACT_RULES: tuple[ArtifactRule, ...] = (
    ArtifactRule(
        "crawler.CrawledPageMeta", ("session", "normalized_url"), "created_at"
    ),
    ArtifactRule(
        "crawler.CrawlerVisit", ("session", "page_meta", "content_hash"), "visited_at"
    ),
    ArtifactRule(
        "content.ContentMetricSnapshot",
        ("import_job_id", "content_item"),
        "captured_at",
    ),
    ArtifactRule(
        "content.SupersededEmbedding",
        ("content_item", "embedding_model_version", "content_hash", "content_version"),
        "superseded_at",
        "replacement_verified_at",
    ),
    ArtifactRule(
        "content.PassageEmbedding", ("content_item", "passage_index"), "created_at"
    ),
    ArtifactRule(
        "knowledge_graph.PixieWalkVisit",
        ("source_content", "visited_content", "signal_version"),
        # Model has `created_at` (not `updated_at`); rule was a typo
        # caught on 2026-05-09 by the live boot-time audit.
        "created_at",
    ),
    ArtifactRule("ops_feed.OperationEvent", ("dedup_key",), "timestamp"),
    ArtifactRule(
        "suggestions.Suggestion",
        ("pipeline_run", "host", "destination", "host_sentence_text", "anchor_phrase"),
        "updated_at",
        "superseded_at",
    ),
)


def startup_smoke_test_enabled() -> bool:
    """Smoke test runs by default; operator can disable via AppSetting.

    Refactor 2026-05-04: shared coerce_bool — was an inline copy of the
    standard 4-truthy-string parser.
    """
    from apps.api.query_params import coerce_bool

    try:
        from apps.core.models import AppSetting

        value = (
            AppSetting.objects.filter(key="system.startup_smoke_test_enabled")
            .values_list("value", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — AppSetting unavailable on cold-start; default to "smoke on" so operator sees boot issues.
        logger.debug("Startup smoke setting unavailable", exc_info=True)
        return True
    if value is None or value == "":
        return True
    return coerce_bool(value, default=True)


def run_startup_smoke_tests() -> list[str]:
    """Run structural artifact-table checks and return warning messages.

    Side-effect (added 2026-05-10): tables that USED to be flagged but
    no longer are get their historical ``ErrorLog`` rows
    auto-acknowledged. Without this, every fix to the audit leaves a
    pile of stale ``x134``-style warnings on `/error-log` forever — the
    exact UX bug the user surfaced via screenshot. The acknowledge pass
    is gated on the audit returning EMPTY for a given step, so a still-
    failing table keeps its open ErrorLog rows visible.
    """
    if not startup_smoke_test_enabled():
        return []

    warnings: list[str] = []
    flagged_steps: set[str] = set()
    for rule in ARTIFACT_RULES:
        warning = _check_rule(rule)
        if warning:
            try:
                model = apps.get_model(rule.model_label)
                flagged_steps.add(model._meta.db_table)
            except LookupError:
                pass
            warnings.append(warning)
            _log_warning(rule, warning)

    for model in _discover_content_artifact_models():
        if any(rule.model_label == model._meta.label for rule in ARTIFACT_RULES):
            continue
        warning = WARNING_TEMPLATE.format(table_name=model._meta.db_table)
        flagged_steps.add(model._meta.db_table)
        warnings.append(warning)
        _log_warning_for_table(model._meta.db_table, warning)

    _auto_acknowledge_resolved_smoke_warnings(flagged_steps)
    return warnings


def _auto_acknowledge_resolved_smoke_warnings(currently_flagged: set[str]) -> int:
    """Mark stale startup_smoke_test ErrorLog rows acknowledged.

    A row is "stale" when its ``step`` (the table name the audit was
    complaining about) is NOT in the current ``currently_flagged`` set.
    Tables that are still flagged keep their open rows visible.

    Returns the count of rows acknowledged so the management-command
    backfill can report progress.
    """
    try:
        from apps.audit.models import ErrorLog
    except Exception:  # noqa: BLE001 — apps.audit may be unavailable on cold-start.
        logger.debug("ErrorLog model unavailable; skipping auto-acknowledge.")
        return 0

    qs = ErrorLog.objects.filter(
        job_type="startup_smoke_test",
        acknowledged=False,
    )
    if currently_flagged:
        qs = qs.exclude(step__in=currently_flagged)
    return qs.update(acknowledged=True)


def _check_rule(rule: ArtifactRule) -> str | None:
    try:
        model = apps.get_model(rule.model_label)
    except LookupError:
        logger.debug("Startup smoke model %s is not installed", rule.model_label)
        return None
    fields = {field.name for field in model._meta.get_fields()}
    if not all(field in fields for field in rule.dedupe_fields):
        return WARNING_TEMPLATE.format(table_name=model._meta.db_table)
    if not _has_unique_invariant(model, rule.dedupe_fields):
        return WARNING_TEMPLATE.format(table_name=model._meta.db_table)
    if rule.retention_field and rule.retention_field not in fields:
        return WARNING_TEMPLATE.format(table_name=model._meta.db_table)
    if rule.supersede_field and rule.supersede_field not in fields:
        return WARNING_TEMPLATE.format(table_name=model._meta.db_table)
    return None


def _has_unique_invariant(model: type[models.Model], fields: tuple[str, ...]) -> bool:
    expected = tuple(fields)
    for item in model._meta.unique_together or ():
        if tuple(item) == expected:
            return True
    for constraint in model._meta.constraints:
        if (
            isinstance(constraint, models.UniqueConstraint)
            and tuple(constraint.fields) == expected
        ):
            return True
    if len(expected) == 1:
        try:
            return bool(model._meta.get_field(expected[0]).unique)
        except Exception:  # noqa: BLE001  # Field-meta lookup can FieldDoesNotExist on alias names; treating "no such field" as "no unique invariant" is the right semantic — the rule will fire and the operator will see the warning.
            return False
    return False


def _discover_content_artifact_models() -> Iterable[type[models.Model]]:
    marker_fields = {
        "content_hash",
        "signal_version",
        "embedding_text_hash",
        "superseded_at",
    }
    # Models that legitimately carry a marker field but are NOT per-content
    # artefacts — they are the parent / canonical tables themselves, or
    # operator-state tables where the marker means something different.
    # Discovery walk skips them so the audit doesn't false-flag.
    excluded_canonical_tables = {
        # ContentItem IS the content. A child table would derive from it
        # (e.g. ContentItem.embedding); the parent itself is excluded.
        "content.ContentItem",
    }
    for model in apps.get_models():
        if model._meta.app_label not in {
            "analytics",
            "content",
            "crawler",
            "knowledge_graph",
            "ops_feed",
            "pipeline",
            "suggestions",
        }:
            continue
        if model._meta.label in excluded_canonical_tables:
            continue
        field_names = {field.name for field in model._meta.get_fields()}
        if marker_fields & field_names:
            yield model


def _log_warning(rule: ArtifactRule, warning: str) -> None:
    model = apps.get_model(rule.model_label)
    _log_warning_for_table(model._meta.db_table, warning)


def _log_warning_for_table(table_name: str, warning: str) -> None:
    try:
        from apps.audit.error_ingest import ingest_error

        ingest_error(
            job_type="startup_smoke_test",
            step=table_name,
            error_message=warning,
            severity="warning",
            why="A content-derived artifact table is missing its structural safety declaration.",
        )
    except Exception:
        logger.warning(warning, exc_info=True)


__all__ = [
    "ARTIFACT_RULES",
    "WARNING_TEMPLATE",
    "run_startup_smoke_tests",
    "startup_smoke_test_enabled",
]
