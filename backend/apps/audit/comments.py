"""
Phase DC / Gaps 128 + 129 — Inline comments on any entity, with
@mention parsing.

Design mirrors the existing ``AuditEntry`` / ``EntityVersion`` pattern:
one flat table keyed by ``(target_type, target_id)`` so any model in
the project can grow a comment thread without its own junction.

Mentions: any substring matching ``@<username>`` in the body is
extracted at save time and stored alongside the row so the
notifications layer (``apps.notifications``) can raise an alert for
each mentioned user.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import models


_MENTION_RE = re.compile(r"(?:^|[\\s(,;])@([A-Za-z0-9_.-]{2,50})")


class EntityComment(models.Model):
    """A single inline comment on any entity."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    target_type = models.CharField(max_length=60, db_index=True)
    target_id = models.CharField(max_length=100, db_index=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="entity_comments",
    )
    body = models.TextField()
    # Cached list of usernames extracted from the body at save time.
    mentions = models.JSONField(default=list, blank=True)
    # Optional parent-comment id for shallow threading.
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    resolved = models.BooleanField(default=False, db_index=True)

    class Meta:
        app_label = "audit"
        verbose_name = "Entity Comment"
        verbose_name_plural = "Entity Comments"
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["target_type", "target_id", "created_at"],
                name="audit_ec_target_idx",
            ),
            models.Index(
                fields=["resolved", "-created_at"],
                name="audit_ec_resolved_idx",
            ),
        ]

    def save(self, *args, **kwargs):  # noqa: D401
        self.mentions = extract_mentions(self.body or "")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"comment#{self.pk} on {self.target_type}:{self.target_id}"


def extract_mentions(body: str) -> list[str]:
    """Return a deduped list of usernames referenced via ``@name``.

    Keeps ordering by first-mention for debuggability. Usernames are
    matched case-insensitively but stored in lowercase so two
    different casings don't notify the same person twice.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _MENTION_RE.finditer(body):
        name = match.group(1).lower()
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
