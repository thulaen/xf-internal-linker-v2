from __future__ import annotations

from django.db import models
from django.utils import timezone


class AgentWorkClaim(models.Model):
    STATUS_CLAIMED = "claimed"
    STATUS_CONFLICTED = "conflicted"
    STATUS_RELEASED = "released"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = (
        (STATUS_CLAIMED, "Claimed"),
        (STATUS_CONFLICTED, "Conflicted"),
        (STATUS_RELEASED, "Released"),
        (STATUS_COMPLETED, "Completed"),
    )

    item_kind = models.CharField(max_length=24, db_index=True)
    item_id = models.PositiveIntegerField(db_index=True)
    item_key = models.CharField(max_length=64, db_index=True)
    agent = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, db_index=True)
    affected_files = models.JSONField(default=list, blank=True)
    conflict_reason = models.TextField(blank=True, default="")
    claimed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)
    next_action = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["item_kind", "item_id", "status"]),
            models.Index(fields=["agent", "status", "claimed_at"]),
        ]

    def release(self) -> None:
        self.status = self.STATUS_RELEASED
        self.released_at = timezone.now()
        self.save(update_fields=["status", "released_at"])


class AgentRepairAttempt(models.Model):
    RESULT_STARTED = "started"
    RESULT_FAILED = "failed"
    RESULT_BLOCKED = "blocked"
    RESULT_PASSED = "passed"
    RESULT_CHOICES = (
        (RESULT_STARTED, "Started"),
        (RESULT_FAILED, "Failed"),
        (RESULT_BLOCKED, "Blocked"),
        (RESULT_PASSED, "Passed"),
    )

    item_kind = models.CharField(max_length=24, db_index=True)
    item_id = models.PositiveIntegerField(db_index=True)
    item_key = models.CharField(max_length=64, db_index=True)
    agent = models.CharField(max_length=80, db_index=True)
    attempt_fingerprint = models.CharField(max_length=64, db_index=True)
    result = models.CharField(max_length=16, choices=RESULT_CHOICES, db_index=True)
    command = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")
    blocker = models.TextField(blank=True, default="")
    next_action = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["item_key", "agent", "attempt_fingerprint"]),
            models.Index(fields=["result", "created_at"]),
        ]


class SelfHealingDecision(models.Model):
    STATUS_WATCHING = "watching"
    STATUS_BLOCKED = "blocked"
    STATUS_REVERT_RECOMMENDED = "revert_recommended"
    STATUS_REVERTED = "reverted"
    STATUS_MANUAL_REVIEW = "manual_review"
    STATUS_CHOICES = (
        (STATUS_WATCHING, "Watching"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_REVERT_RECOMMENDED, "Revert recommended"),
        (STATUS_REVERTED, "Reverted"),
        (STATUS_MANUAL_REVIEW, "Manual review"),
    )

    latest_commit_sha = models.CharField(max_length=64, blank=True, default="")
    latest_commit_author = models.CharField(max_length=160, blank=True, default="")
    agent_authored = models.BooleanField(default=False)
    backend_health = models.CharField(max_length=24, default="unknown")
    frontend_health = models.CharField(max_length=24, default="unknown")
    dirty_worktree = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, db_index=True)
    reason = models.TextField(blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class SourceConfidence(models.Model):
    source = models.CharField(max_length=64, unique=True)
    trust_score = models.FloatField(default=0.5)
    reason = models.TextField(blank=True, default="")
    evidence_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source"]

