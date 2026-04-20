"""
Audit models — full audit trail, reviewer scorecards, and error log.

Every significant action in the app is logged to AuditEntry.
This provides a complete history of who approved what, and when.
"""

from django.db import models


class AuditEntry(models.Model):
    """
    Immutable log of every significant action taken in the application.

    Covers suggestion reviews, setting changes, plugin toggles, and more.
    Records are never deleted — they form a permanent audit trail.
    """

    ACTION_CHOICES = [
        ("approve", "Approved suggestion"),
        ("reject", "Rejected suggestion"),
        ("apply", "Marked as applied"),
        ("verify", "Verified live link"),
        ("edit_anchor", "Edited anchor text"),
        ("mark_stale", "Marked as stale"),
        ("supersede", "Superseded"),
        ("note", "Note added"),
        ("setting_change", "Setting changed"),
        ("plugin_toggle", "Plugin enabled/disabled"),
        ("pipeline_start", "Pipeline run started"),
        ("pipeline_complete", "Pipeline run completed"),
        ("sync_start", "Sync started"),
        ("sync_complete", "Sync completed"),
        ("clear_suppression", "Cleared rejected-pair suppression"),
    ]

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        db_index=True,
        help_text="What type of action was taken.",
    )
    target_type = models.CharField(
        max_length=50,
        help_text="The model/entity type affected, e.g. 'suggestion', 'setting', 'plugin'.",
    )
    target_id = models.CharField(
        max_length=100,
        help_text="The primary key of the affected record.",
    )
    detail = models.JSONField(
        default=dict,
        help_text="Extra context: previous value, new value, reason, etc.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user who took this action.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this action was recorded.",
    )

    class Meta:
        verbose_name = "Audit Entry"
        verbose_name_plural = "Audit Trail"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.action}] {self.target_type}:{self.target_id} at {self.created_at}"
        )


class ReviewerScorecard(models.Model):
    """
    Aggregated reviewer performance metrics for a time period.

    Calculated periodically (e.g. weekly) to show how the reviewer
    is performing: approval rate, how many applied links stayed live, etc.
    """

    period_start = models.DateField(
        help_text="Start date of the reporting period.",
    )
    period_end = models.DateField(
        help_text="End date of the reporting period.",
    )
    total_reviewed = models.IntegerField(
        default=0,
        help_text="Total suggestions reviewed in this period.",
    )
    approved_count = models.IntegerField(
        default=0,
        help_text="Number of suggestions approved.",
    )
    rejected_count = models.IntegerField(
        default=0,
        help_text="Number of suggestions rejected.",
    )
    approval_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of reviewed suggestions that were approved.",
    )
    verified_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of approved suggestions later verified as live.",
    )
    stale_rate = models.FloatField(
        default=0.0,
        help_text="Percentage of approved suggestions that went stale.",
    )
    avg_review_time_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Average seconds per suggestion review decision.",
    )
    top_rejection_reasons = models.JSONField(
        default=list,
        help_text="Top rejection reason codes and their counts for this period.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this scorecard was generated.",
    )

    class Meta:
        verbose_name = "Reviewer Scorecard"
        verbose_name_plural = "Reviewer Scorecards"
        ordering = ["-period_end"]

    def __str__(self) -> str:
        return f"Scorecard {self.period_start} → {self.period_end} ({self.total_reviewed} reviewed)"


class ErrorLog(models.Model):
    """
    Centralized error log for background job failures.

    Errors from Celery tasks (import, embed, pipeline, sync) are written here
    so the user can see what went wrong without needing to read Docker logs.

    Phase GT expands this into the operator intelligence layer — GlitchTip
    sync, plain-English fix suggestions, multi-node attribution, and runtime
    context captured at crash time. Historic rows continue to work with only
    the original fields populated; new fields default safely.
    """

    # ── Source / dedup ────────────────────────────────────────────
    SOURCE_INTERNAL = "internal"
    SOURCE_GLITCHTIP = "glitchtip"
    SOURCE_CHOICES = [
        (SOURCE_INTERNAL, "Internal"),
        (SOURCE_GLITCHTIP, "GlitchTip"),
    ]

    # ── Severity ──────────────────────────────────────────────────
    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_LOW, "Low"),
    ]

    # ── Node role (forward-compatible with K8s/Lightsail/slaves) ──
    NODE_ROLE_PRIMARY = "primary"
    NODE_ROLE_CHOICES = [
        (NODE_ROLE_PRIMARY, "Primary"),
        ("worker", "Worker"),
        ("celery", "Celery"),
        ("lightsail", "Lightsail"),
        ("k8s", "K8s Pod"),
        ("slave", "Slave"),
        ("unknown", "Unknown"),
    ]

    # ── Existing fields ───────────────────────────────────────────
    job_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of job that failed, e.g. 'import', 'embed', 'pipeline', 'sync'.",
    )
    step = models.CharField(
        max_length=100,
        help_text="The specific step or function where the error occurred.",
    )
    error_message = models.TextField(
        help_text="Human-readable error message.",
    )
    raw_exception = models.TextField(
        blank=True,
        help_text="Full Python traceback (for debugging).",
    )
    why = models.TextField(
        blank=True,
        help_text="Plain-English explanation of what likely caused this error.",
    )
    acknowledged = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True once the user has reviewed and dismissed this error.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this error was recorded.",
    )

    # ── GT Phase: source + dedup + GlitchTip linkage ──────────────
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_INTERNAL,
        db_index=True,
        help_text="Origin of this entry: internal (Celery tasks) or glitchtip (sync task).",
    )
    glitchtip_issue_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        help_text="Issue id from GlitchTip when source='glitchtip'.",
    )
    glitchtip_url = models.URLField(
        null=True,
        blank=True,
        help_text="Deep link to the GlitchTip issue detail page.",
    )
    fingerprint = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Normalised hash used to dedupe repeat occurrences. "
            "Internal: sha1(job|step|normalize(message)). GlitchTip: their fingerprint."
        ),
    )
    occurrence_count = models.IntegerField(
        default=1,
        help_text="Number of times this fingerprint has been seen on this node.",
    )
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_MEDIUM,
        db_index=True,
    )

    # ── GT Phase: plain-English triage field ──────────────────────
    how_to_fix = models.TextField(
        blank=True,
        help_text="Plain-English fix suggestion surfaced to the operator.",
    )

    # ── GT Phase: helper-node attribution ─────────────────────────
    node_id = models.CharField(
        max_length=100,
        default=NODE_ROLE_PRIMARY,
        db_index=True,
        help_text="Identifier of the node that produced this error.",
    )
    node_role = models.CharField(
        max_length=20,
        choices=NODE_ROLE_CHOICES,
        default=NODE_ROLE_PRIMARY,
        db_index=True,
    )
    node_hostname = models.CharField(max_length=255, blank=True)

    # ── GT Phase: runtime snapshot at crash time ──────────────────
    runtime_context = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Snapshot produced by apps.audit.runtime_context.snapshot() — "
            "GPU/CUDA/embedding/spaCy/python/node at the moment of failure."
        ),
    )

    class Meta:
        verbose_name = "Error Log Entry"
        verbose_name_plural = "Error Log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["acknowledged", "-created_at"]),
            models.Index(fields=["source", "glitchtip_issue_id"]),
            models.Index(fields=["fingerprint", "acknowledged"]),
            models.Index(fields=["node_id", "-created_at"]),
        ]
        constraints = [
            # One row per (fingerprint, node_id) so the same error on the
            # same node dedupes to occurrence_count++ instead of a new row.
            # Different nodes get separate rows — intentional for slave/
            # helper attribution. NULL fingerprints are excluded.
            models.UniqueConstraint(
                fields=["fingerprint", "node_id"],
                condition=models.Q(fingerprint__isnull=False),
                name="uniq_errorlog_fingerprint_per_node",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.job_type}:{self.step}] {self.error_message[:80]}"


class ClientErrorLog(models.Model):
    """
    Phase U1 / Gap 26 — unhandled frontend exceptions reported via
    `POST /api/telemetry/client-errors/`.

    Captured by the Angular `GlobalErrorHandler` whenever:
    - Sentry/GlitchTip is NOT configured (DSN empty), OR
    - You want a local copy of client errors even when Sentry is on.

    Kept deliberately narrow: route + message + stack + user agent + a
    few optional hints. No PII. Browser-side IP arrives via the standard
    request metadata and is not stored separately.

    Dedup strategy is intentionally looser than `ErrorLog` — client
    errors are triage noise until a pattern emerges, so each report gets
    its own row. A future session (Phase U2) can add fingerprint-based
    grouping if needed.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # What broke
    message = models.TextField(help_text="Error message as seen by the browser.")
    stack = models.TextField(
        blank=True,
        help_text="Stack trace, if the browser provided one.",
    )

    # Where
    route = models.CharField(
        max_length=500,
        blank=True,
        help_text="The Angular router URL at time of error.",
    )
    url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Full document.location.href at time of error.",
    )

    # Client fingerprint (low-entropy)
    user_agent = models.CharField(max_length=500, blank=True)
    app_version = models.CharField(max_length=50, blank=True)

    # Optional links
    user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Authenticated user id, if known. Not a FK — decoupled from the User table.",
    )

    # Free-form extras
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured context captured with the error (feature flags, scope, etc.).",
    )

    class Meta:
        verbose_name = "Client Error Log Entry"
        verbose_name_plural = "Client Error Log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["route", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.route or '?'}] {self.message[:80]}"


class WebVital(models.Model):
    """
    Phase E2 / Gap 51 — Core Web Vitals measurements reported by the
    frontend's `WebVitalsService` via `POST /api/telemetry/web-vitals/`.

    One row per metric fire per page-load. The frontend uses the
    `web-vitals` library which fires each metric at most once per
    navigation (with INP being an exception — it can update as the
    worst-so-far interaction grows). We keep every sample so the
    Performance Dashboard (Gap 130) can chart p75/p95 percentiles.

    Deliberately narrow: no user-agent fingerprint beyond device_memory
    and effective connection type. IP is not stored. Auth-optional
    because we want to capture vitals on the login page too.

    Dedup / retention: the Performance Dashboard query layer aggregates
    on its own. This table is the raw event log. A future session can
    add a cleanup task if the table grows unmanageable (pragma: only
    five fires per page per user; at 10k sessions/day ~= 50k rows/day,
    ~= 18M/year — well within Postgres comfort).
    """

    # Web Vitals metric names per the library — keep in lockstep with
    # the `onLCP` / `onCLS` / `onINP` / `onFCP` / `onTTFB` call sites.
    METRIC_CHOICES = [
        ("LCP", "Largest Contentful Paint"),
        ("CLS", "Cumulative Layout Shift"),
        ("INP", "Interaction to Next Paint"),
        ("FCP", "First Contentful Paint"),
        ("TTFB", "Time to First Byte"),
    ]

    # Per library's rating rubric (good/needs-improvement/poor).
    RATING_CHOICES = [
        ("good", "Good"),
        ("needs-improvement", "Needs improvement"),
        ("poor", "Poor"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # What was measured
    name = models.CharField(max_length=10, choices=METRIC_CHOICES, db_index=True)
    value = models.FloatField(
        help_text="Metric value. Milliseconds for timings (LCP/INP/FCP/TTFB), unitless for CLS.",
    )
    rating = models.CharField(
        max_length=20,
        choices=RATING_CHOICES,
        default="good",
        db_index=True,
    )
    delta = models.FloatField(
        default=0.0,
        help_text="Change since the last fire of this metric this page-load (for INP monotonic growth).",
    )

    # Identity
    metric_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Library-assigned unique id per metric per page-load.",
    )
    navigation_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="'navigate' | 'reload' | 'back-forward' | 'prerender' | 'restore'.",
    )

    # Where (pathname only — NOT full URL to avoid query-string PII)
    path = models.CharField(max_length=500, blank=True, db_index=True)

    # Client tier hints (no UA, no IP)
    device_memory = models.FloatField(
        null=True,
        blank=True,
        help_text="navigator.deviceMemory when available (1, 2, 4, 8 GB tiers).",
    )
    effective_connection_type = models.CharField(
        max_length=10,
        blank=True,
        help_text="'4g' / '3g' / '2g' / 'slow-2g' — navigator.connection.effectiveType.",
    )

    # Client clock (ms since epoch) — distinct from server-side created_at
    # so we can reason about very old beacons delivered after page close.
    client_timestamp_ms = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Client-side Date.now() at metric fire time.",
    )

    # Optional
    user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Authenticated user id, if known. Not a FK — decoupled from the User table.",
    )

    class Meta:
        verbose_name = "Web Vital Measurement"
        verbose_name_plural = "Web Vital Measurements"
        ordering = ["-created_at"]
        indexes = [
            # Dashboard query: "LCP on /dashboard for the last 7 days"
            models.Index(fields=["name", "path", "-created_at"]),
            models.Index(fields=["name", "rating", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name}={self.value:.2f} [{self.rating}] @ {self.path or '/'}"


# Phase DC / Gap 119 — Version history table.
# Defined in ``version_history.py`` to keep this file at a reasonable
# size; re-exported here so Django's app registry picks it up during
# auto-discovery and ``makemigrations``.
from .version_history import EntityVersion  # noqa: E402, F401

# Phase DC / Gaps 128 + 129 — Comments + @mention extraction.
from .comments import EntityComment  # noqa: E402, F401

# Phase GB / Gap 151 — Feature-Request inbox + per-user vote rows.
from .feature_requests import FeatureRequest, FeatureRequestVote  # noqa: E402, F401
