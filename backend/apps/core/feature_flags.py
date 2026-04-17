"""
Phase OB / Gaps 131 + 132 — Feature flag model + A/B variant hashing.

Single table keyed by a stable ``key`` string. Rolls out to a
percentage of authenticated users via a deterministic hash of
(user_id, flag_key) → [0, 99]. Variant selection uses the same
hashing strategy — the user lands in the variant whose weight bucket
covers their hash.

Admin UI: the model registers with Django admin so site operators
can flip flags without a code deploy. The frontend fetches the
effective flag set from ``/api/feature-flags/``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import models


class FeatureFlag(models.Model):
    """A single feature flag.

    When ``variants`` is empty, this is a simple on/off flag and the
    exposed ``variant`` field in the API response will be omitted.
    When ``variants`` is set (list of ``{name: str, weight: int}``),
    the user is deterministically assigned one variant based on a
    stable hash of ``(user_id, key)``.
    """

    key = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=False)
    #: Percentage of eligible users who see this flag (0-100). Only
    #: applies when ``enabled=True``.
    rollout_percent = models.PositiveSmallIntegerField(default=100)
    #: Optional A/B variants. Shape::
    #:    [{"name": "control", "weight": 50}, {"name": "new-cta", "weight": 50}]
    #: Weights don't need to sum to 100 — they're normalised internally.
    variants = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "core"
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} ({'on' if self.enabled else 'off'})"

    # ── evaluation ─────────────────────────────────────────────────────

    def is_active_for(self, user_id: Optional[int]) -> bool:
        """Is this flag on for the given user?

        Anonymous requests (``user_id is None``) are eligible only
        when ``rollout_percent == 100`` — otherwise we'd need a
        stable pseudo-id and the current behaviour errs on the
        "don't leak unfinished features" side.
        """
        if not self.enabled:
            return False
        if self.rollout_percent >= 100:
            return True
        if user_id is None:
            return False
        return _bucket(user_id, self.key) < self.rollout_percent

    def variant_for(self, user_id: Optional[int]) -> Optional[str]:
        """Resolve the variant name the user lands in, or ``None``
        when the flag has no variants configured.
        """
        if not self.variants:
            return None
        total = sum(max(0, int(v.get("weight", 0))) for v in self.variants)
        if total <= 0:
            return None
        bucket = _bucket(user_id or 0, f"{self.key}:variant")
        running = 0
        scale = 100 / total
        for variant in self.variants:
            running += max(0, int(variant.get("weight", 0))) * scale
            if bucket < running:
                return str(variant.get("name", "")) or None
        return str(self.variants[-1].get("name", "")) or None


class FeatureFlagExposure(models.Model):
    """A record of "user saw flag X in variant Y" for analytics."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    key = models.SlugField(max_length=80, db_index=True)
    variant = models.CharField(max_length=60, blank=True)
    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_flag_exposures",
    )

    class Meta:
        app_label = "core"
        verbose_name = "Feature Flag Exposure"
        verbose_name_plural = "Feature Flag Exposures"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["key", "-created_at"],
                name="core_ffexp_key_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key}={self.variant or 'on'} @ {self.created_at:%Y-%m-%d}"


def _bucket(user_id: int, salt: str) -> int:
    """Deterministic 0-99 bucket for a (user, salt) pair."""
    h = hashlib.sha256(f"{user_id}:{salt}".encode("utf-8")).hexdigest()
    # Take the first 8 hex chars → 32-bit int → modulo 100.
    return int(h[:8], 16) % 100


def serialise_for_user(user_id: Optional[int]) -> list[dict]:
    """Return the flag snapshot shape the frontend expects."""
    out: list[dict] = []
    for flag in FeatureFlag.objects.all():
        if not flag.is_active_for(user_id):
            continue
        entry: dict[str, object] = {"key": flag.key, "enabled": True}
        variant = flag.variant_for(user_id)
        if variant:
            entry["variant"] = variant
        out.append(entry)
    return out


__all__ = ["FeatureFlag", "FeatureFlagExposure", "serialise_for_user"]
