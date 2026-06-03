"""Controlled vocabulary for cross-area AutoIssue lesson retrieval."""

from __future__ import annotations

from django.core.management.base import CommandError
from django.db.models import Q


ALLOWED_CONCEPT_TAGS = frozenset(
    {
        "python-subprocess",
        "windows-encoding",
        "django-migration",
        "django-management-command",
        "mutable-default",
        "on-delete-fk",
        "raw-sql",
        "hook-marker-format",
        "bdd-fields",
        "citation-format",
        "glitchtip-integration",
        "pgdata-protection",
        "docker-volume-mount",
        "writable-layer",
        "celery-worker",
        "profiling-proof",
        "performance-exemption",
        "spec-citation",
        "canonical-fingerprint",
        "tdd-cycle-strict",
    }
)


def validate_tag(tag: str) -> None:
    """Raise a plain-English command error when a concept tag is unknown."""
    if tag not in ALLOWED_CONCEPT_TAGS:
        raise CommandError(
            f"unknown concept tag {tag!r}. Run `manage.py list_concept_tags` "
            f"to see the {len(ALLOWED_CONCEPT_TAGS)} accepted tags."
        )


def collect_and_validate_tags(options: dict, *, key: str = "concept_tag") -> list[str]:
    """Return approved tags from a management command options dictionary."""
    tags = [str(tag).strip() for tag in options.get(key, []) if str(tag).strip()]
    unique_tags = list(dict.fromkeys(tags))
    for tag in unique_tags:
        validate_tag(tag)
    return unique_tags


def merge_tags(existing: list[str] | None, new_tags: list[str]) -> list[str]:
    """Preserve existing order while adding newly supplied approved tags."""
    return list(dict.fromkeys([*(existing or []), *new_tags]))


def build_tag_query(tags: list[str]) -> Q:
    """Build the AutoIssue filter for any overlap with approved tags."""
    if not tags:
        return Q()
    return Q(concept_tags__overlap=tags)
