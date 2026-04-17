"""
Phase GB / Gap 151 — In-app Feature-Request inbox.

Operators and admins can submit a "Suggest a feature" form from anywhere
in the UI. Submissions land in this table so maintainers have a single
queue to triage, instead of scattered Slack messages and support emails.

Schema design:
- ``title`` is short, ``body`` is the long-form pitch.
- ``category`` is a free-form tag (UI / backend / performance / …) so
  maintainers can slice the queue without a rigid taxonomy.
- ``priority`` is self-declared by the submitter; maintainers may
  override via Django Admin or the future triage UI.
- ``status`` is the triage lifecycle. New rows start in ``new``; admin
  actions flip them through ``accepted`` / ``planned`` / ``shipped`` /
  ``declined`` / ``duplicate``.
- ``context`` captures the page + UA + locale so maintainers can
  reproduce environmental quirks without emailing back and forth.
- ``votes`` lets maintainers quickly rank what other operators want.

Notifications: the admin-queue size is exposed via /api/feature-requests/
with a ``status=new`` filter. A future digest task can email maintainers
when the queue grows past a threshold.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class FeatureRequest(models.Model):
    """One operator-submitted feature request."""

    PRIORITY_CHOICES = [
        ("low", "Low — nice to have"),
        ("medium", "Medium — would help regularly"),
        ("high", "High — blocks my workflow"),
    ]
    STATUS_CHOICES = [
        ("new", "New"),
        ("accepted", "Accepted"),
        ("planned", "Planned"),
        ("shipped", "Shipped"),
        ("declined", "Declined"),
        ("duplicate", "Duplicate"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="feature_requests",
    )
    title = models.CharField(max_length=160)
    body = models.TextField()
    category = models.CharField(max_length=40, blank=True, db_index=True)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium", db_index=True
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="new", db_index=True
    )
    # Free-form environmental context captured at submit time — route,
    # user agent, locale, screen size. Shape is intentionally open;
    # admins render as raw JSON in the triage UI.
    context = models.JSONField(default=dict, blank=True)
    # Lightweight upvote counter. +1 per authenticated "me too" click
    # from another operator. Dedup is enforced in the view, not the
    # model, to keep writes cheap.
    votes = models.IntegerField(default=0)
    # Free-form triage response — visible to the submitter in the UI.
    admin_reply = models.TextField(blank=True)

    class Meta:
        app_label = "audit"
        verbose_name = "Feature Request"
        verbose_name_plural = "Feature Requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="audit_fr_status_idx"),
            models.Index(
                fields=["priority", "-created_at"], name="audit_fr_priority_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"feature-request#{self.pk}: {self.title}"


class FeatureRequestVote(models.Model):
    """A single operator's upvote on a FeatureRequest — enforces one-per-user."""

    created_at = models.DateTimeField(auto_now_add=True)
    request = models.ForeignKey(
        FeatureRequest, on_delete=models.CASCADE, related_name="vote_rows"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feature_votes",
    )

    class Meta:
        app_label = "audit"
        verbose_name = "Feature Request Vote"
        verbose_name_plural = "Feature Request Votes"
        constraints = [
            models.UniqueConstraint(
                fields=["request", "user"], name="uniq_feature_vote_per_user"
            ),
        ]
