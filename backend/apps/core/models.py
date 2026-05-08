"""
Core shared models for XF Internal Linker V2.

All app models inherit from TimestampedModel to get created_at / updated_at.
AppSetting stores typed key-value configuration for the application.
"""

from django.db import models


class TimestampedModel(models.Model):
    """
    Abstract base model that adds created_at and updated_at to every model.
    All V2 models should inherit from this.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this record was last modified.",
    )

    class Meta:
        abstract = True


class AppSetting(TimestampedModel):
    """
    Application-wide configuration stored in the database.
    Replaces hardcoded settings for things the user may want to change
    without restarting Docker (e.g. pipeline weights, API keys, sync schedule).
    """

    CATEGORY_CHOICES = [
        ("general", "General"),
        ("ml", "ML / AI"),
        ("link_freshness", "Link Freshness"),
        ("sync", "Sync"),
        ("performance", "Performance"),
        ("api", "API Keys"),
        ("analytics", "Analytics"),
        ("anchor", "Anchor Policy"),
        ("appearance", "Appearance"),
    ]

    VALUE_TYPE_CHOICES = [
        ("str", "Text"),
        ("int", "Integer"),
        ("float", "Decimal"),
        ("bool", "True / False"),
        ("json", "JSON"),
    ]

    key = models.CharField(
        max_length=200,
        unique=True,
        help_text="Unique setting key, e.g. 'pipeline.max_links_per_host'.",
    )
    value = models.TextField(
        help_text="Stored value (always text; cast using value_type).",
    )
    value_type = models.CharField(
        max_length=20,
        choices=VALUE_TYPE_CHOICES,
        default="str",
        help_text="Data type of the value — used to cast when reading.",
    )
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="general",
        db_index=True,
        help_text="Grouping shown in the admin sidebar.",
    )
    description = models.CharField(
        max_length=500,
        help_text="Human-readable description of what this setting controls.",
    )
    is_secret = models.BooleanField(
        default=False,
        help_text="If True, the value is masked in the admin UI (e.g. API keys).",
    )

    class Meta:
        verbose_name = "App Setting"
        verbose_name_plural = "App Settings"
        ordering = ["category", "key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value if not self.is_secret else '••••••••'}"

    # ─────────────────────────────────────────────────────────────────
    # Type-cast getters (Group D consolidation, 2026-04-28)
    #
    # Plain English: every place in the codebase that reads an
    # ``AppSetting`` value did its own ``.objects.filter(key=...).first()``
    # plus its own try/except cast. That pattern was duplicated across
    # ~10 files (cooccurrence/tasks.py, health/services.py,
    # sync/services/webhooks.py, suggestions/readiness.py, and so on).
    # These classmethods centralise the cast + miss-fallback so the
    # callers shrink to one line and the parse semantics stay
    # consistent across the project.
    #
    # All getters:
    #   * Never raise on missing key, blank value, or parse failure —
    #     they return the supplied ``default``.
    #   * Are safe to call from any session / queue / worker context.
    #   * Match the existing "value.strip().lower() == 'true'" boolean
    #     convention used by ``recommended_bool``.
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_str(cls, key: str, default: str = "") -> str:
        """Return the AppSetting's text value, or ``default`` on miss."""
        try:
            row = cls.objects.filter(key=key).only("value").first()
        except Exception:  # noqa: BLE001  # Settings reader is called from cold-start paths where the table may not yet exist (post_migrate, mid-migration). Return the default rather than crash boot.
            return default
        if row is None or row.value is None:
            return default
        return row.value

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Return the AppSetting's value cast to int, or ``default`` on miss / parse fail."""
        raw = cls.get_str(key, "")
        if not raw:
            return default
        try:
            # Allow operators to type "5.0" or " 5 " in the admin UI.
            return int(float(raw.strip()))
        except (TypeError, ValueError):
            return default

    @classmethod
    def get_float(cls, key: str, default: float = 0.0) -> float:
        """Return the AppSetting's value cast to float, or ``default`` on miss / parse fail."""
        raw = cls.get_str(key, "")
        if not raw:
            return default
        try:
            return float(raw.strip())
        except (TypeError, ValueError):
            return default

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Return the AppSetting's value cast to bool, or ``default`` on miss.

        Recognises the canonical Recommended-preset format (``"true"`` ⇒ True,
        anything else ⇒ False — matching ``recommended_bool``) plus operator-
        friendly variants ``1`` / ``yes`` / ``on`` / ``0`` / ``no`` / ``off``.
        Unknown values fall back to ``default``.

        Refactor 2026-05-04: parse_bool_strict from apps.api.query_params is
        the single source of truth for the 3-way truthy/falsy/unknown
        semantics. Previously this method was the original ancestor of the
        4-truthy-string parser duplication that proliferated across the app.
        """
        from apps.api.query_params import parse_bool_strict

        raw = cls.get_str(key, "")
        if not raw:
            return default
        return parse_bool_strict(raw, default=default)

    @classmethod
    def get_json(cls, key: str, default=None):
        """Return the AppSetting's value parsed as JSON, or ``default`` on miss / parse fail."""
        raw = cls.get_str(key, "")
        if not raw:
            return default
        import json as _json

        try:
            return _json.loads(raw)
        except (TypeError, ValueError):
            return default


class HelperNode(TimestampedModel):
    """A registered helper node for distributed workload execution (Stage 8/10).

    See docs/PERFORMANCE.md §10 for the multi-node architecture.
    """

    TIME_POLICY_CHOICES = [
        ("anytime", "Available anytime"),
        ("nighttime", "Nighttime only (21:00–06:00 UTC)"),
        ("maintenance", "Maintenance windows only"),
    ]

    # Heartbeat status enum. The HelperNodeHeartbeatView uses this set
    # to validate operator-supplied status values so a buggy reporter
    # can't set status to a list / dict / unknown string. Kept as a
    # frozenset on the model so the view can `import HelperNode` and
    # do `if status in HelperNode.VALID_HEARTBEAT_STATUSES`.
    VALID_HEARTBEAT_STATUSES = frozenset({"online", "busy", "stale", "offline"})

    name = models.CharField(max_length=100, unique=True)
    token_hash = models.CharField(
        max_length=128,
        help_text="SHA-256 hash of the registration token. Never store the raw token.",
    )
    role = models.CharField(max_length=50, default="worker")
    capabilities = models.JSONField(
        default=dict,
        help_text='{"cpu_cores": 8, "ram_gb": 16, "gpu_vram_gb": 6, "network_quality": "good"}',
    )
    allowed_queues = models.JSONField(
        default=list,
        help_text='["pipeline", "embeddings"]',
    )
    allowed_job_types = models.JSONField(
        default=list,
        help_text='["sync", "pipeline", "embeddings"]',
    )
    time_policy = models.CharField(
        max_length=20,
        choices=TIME_POLICY_CHOICES,
        default="anytime",
    )
    max_concurrency = models.IntegerField(default=2)
    cpu_cap_pct = models.IntegerField(
        default=60,
        help_text="Maximum CPU usage percentage (safety default: 60%).",
    )
    ram_cap_pct = models.IntegerField(
        default=60,
        help_text="Maximum RAM usage percentage (safety default: 60%).",
    )
    accepting_work = models.BooleanField(
        default=True,
        help_text="Operator toggle that lets the helper stay healthy but stop taking work.",
    )
    status = models.CharField(
        max_length=20,
        default="offline",
        db_index=True,
        help_text="Current state: online, busy, unhealthy, offline.",
    )
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    active_jobs = models.IntegerField(default=0)
    queued_jobs = models.IntegerField(default=0)
    cpu_pct = models.FloatField(default=0.0)
    ram_pct = models.FloatField(default=0.0)
    gpu_util_pct = models.FloatField(null=True, blank=True)
    gpu_vram_used_mb = models.IntegerField(null=True, blank=True)
    gpu_vram_total_mb = models.IntegerField(null=True, blank=True)
    network_rtt_ms = models.IntegerField(null=True, blank=True)
    native_kernels_healthy = models.BooleanField(default=False)
    warmed_model_keys = models.JSONField(
        default=list,
        help_text='["embedding:BAAI/bge-m3:fr020-v1"]',
    )

    class Meta:
        verbose_name = "Helper Node"
        verbose_name_plural = "Helper Nodes"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"


class QuarantineRecord(TimestampedModel):
    """First-class quarantine record (plan item 16).

    Replaces the bare boolean ``PipelineRun.is_quarantined``.  A QuarantineRecord
    stores *why* an item was quarantined, *what* is affected, *which* safe fix
    exists for it (matched against the frontend runbook library), and whether
    it can resume from a checkpoint.  The `PipelineRun.is_quarantined` flag is
    kept for backwards compatibility but is now a mirror of
    ``active QuarantineRecord exists``; new code should read/write via this
    model exclusively.

    Storage estimate: ~500 KB at 30 days with an autoprune at 90 days
    (tracked under plan item 19 retention work).
    """

    REASON_REPEATED_FAILURE = "repeated_failure"
    REASON_BAD_CREDENTIALS = "bad_credentials"
    REASON_MALFORMED_IMPORT = "malformed_import"
    REASON_STALLED_CRAWL = "stalled_crawl"
    REASON_BROKEN_WARMUP = "broken_warmup"
    REASON_DUPLICATE_CONFLICT = "duplicate_conflict"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_REPEATED_FAILURE, "Repeated failures"),
        (REASON_BAD_CREDENTIALS, "Bad credentials"),
        (REASON_MALFORMED_IMPORT, "Malformed import"),
        (REASON_STALLED_CRAWL, "Stalled crawl"),
        (REASON_BROKEN_WARMUP, "Broken warmup"),
        (REASON_DUPLICATE_CONFLICT, "Duplicate conflicting job"),
        (REASON_OTHER, "Other"),
    ]

    # What's quarantined.  Polymorphic pointer: most records point at a
    # PipelineRun today, but the same table can carry sync jobs, suggestions,
    # or crawl sessions tomorrow without a schema change.
    related_object_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="e.g. 'pipeline_run', 'sync_job', 'suggestion', 'crawl_session'.",
    )
    related_object_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Primary key or UUID of the quarantined object as a string.",
    )

    # Why it was quarantined.
    reason = models.CharField(
        max_length=48,
        choices=REASON_CHOICES,
        default=REASON_REPEATED_FAILURE,
        db_index=True,
    )
    reason_detail = models.TextField(
        blank=True,
        help_text="Plain-English extended explanation shown to the user.",
    )

    # Everything else affected by this quarantine (list of ids, paths, or refs).
    affected_items = models.JSONField(
        default=list,
        blank=True,
        help_text='["content_item:123", "sync_job:abc"] — items impacted beyond the primary.',
    )

    # Which runbook from the frontend library can fix this.
    fix_available = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text="Runbook id, e.g. 'reset-quarantined-job' or 'restart-stuck-pipeline'.",
    )

    # Checkpoint resumability.
    resume_from_checkpoint = models.BooleanField(default=False)
    checkpoint_id = models.CharField(
        max_length=128,
        blank=True,
        help_text="Opaque checkpoint handle the worker can pick up at resume.",
    )

    # Lifecycle.
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolved_by = models.CharField(
        max_length=64,
        blank=True,
        help_text="'user', 'auto', or 'runbook:<id>' — who/what closed this.",
    )
    resolved_note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Quarantine Record"
        verbose_name_plural = "Quarantine Records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["related_object_type", "related_object_id"],
                name="qrec_related_idx",
            ),
            models.Index(fields=["resolved_at"], name="qrec_resolved_idx"),
        ]

    # Convenience -----------------------------------------------------

    @property
    def is_open(self) -> bool:
        """True while the quarantine has not been resolved."""
        return self.resolved_at is None

    def __str__(self) -> str:
        state = "open" if self.is_open else "resolved"
        return f"QuarantineRecord<{self.related_object_type}:{self.related_object_id} {self.reason} {state}>"


# Phase OB / Gaps 131 + 132 — Feature flags + A/B variants + exposures.
# Migrated to ``apps.audit`` for unification.
from apps.audit.models import FeatureFlag, FeatureFlagExposure  # noqa: E402, F401
from .runtime_models import (  # noqa: E402, F401
    HardwareCapabilitySnapshot,
    RuntimeAuditLog,
    RuntimeModelBackfillPlan,
    RuntimeModelPlacement,
    RuntimeModelRegistry,
)


class UserActivity(TimestampedModel):
    """Rolling "last seen" heartbeat for each user.

    Written by a Django signal on every DRF-authenticated request so the
    ``whos-on-shift`` dashboard widget and presence heuristics know who
    is active without polling session tables. One row per user.

    Kept small on purpose — no per-request history, no IP, no user-agent.
    If we need granular history we'll add a separate append-only table.
    """

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="activity",
        help_text="User this heartbeat belongs to.",
    )
    last_seen_at = models.DateTimeField(
        db_index=True,
        help_text="Most recent authenticated request from this user.",
    )
    last_route = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="URL path of the most recent request (best-effort).",
    )

    class Meta:
        verbose_name = "User activity heartbeat"
        verbose_name_plural = "User activity heartbeats"

    def __str__(self) -> str:
        return f"UserActivity<{self.user_id} @ {self.last_seen_at.isoformat()}>"


# Phase — passkey / WebAuthn credentials + challenge scratch space.
# Kept in the same file rather than a new module because both tables
# are tiny and only ever touched from ``views_passkey.py``.


class PasskeyCredential(TimestampedModel):
    """Stored WebAuthn credential for a user.

    Written on successful ``/api/auth/passkey/register/finish/`` and read
    on every ``/api/auth/passkey/login/begin|finish/`` roundtrip.
    """

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="passkey_credentials",
    )
    credential_id = models.BinaryField(
        unique=True,
        help_text="Raw credential-id bytes (opaque, unique per credential).",
    )
    public_key = models.BinaryField(
        help_text="COSE-encoded public key used to verify login assertions.",
    )
    sign_count = models.PositiveBigIntegerField(
        default=0,
        help_text="Monotonic counter — increments on each successful login.",
    )
    transports = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Comma-separated transport hints (usb,nfc,ble,internal,hybrid).",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Human label the user gave this credential at register time.",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "last_used_at"], name="pkc_user_used_idx"),
        ]

    def __str__(self) -> str:
        return f"PasskeyCredential<user={self.user_id} label={self.label!r}>"


class PasskeyChallenge(TimestampedModel):
    """Short-lived challenge issued during register/login begin.

    The ``finish`` step looks up the matching row by ``challenge`` and
    ``operation_type``, verifies the assertion, and deletes the row.
    Rows older than 5 minutes are swept by the finish handler.
    """

    OPERATION_CHOICES = [
        ("register", "Register"),
        ("login", "Login"),
    ]

    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="passkey_challenges",
        null=True,
        blank=True,
        help_text="User the challenge was issued to. Null for anonymous login-begin "
        "(the user is identified by the credential they return).",
    )
    operation_type = models.CharField(
        max_length=20,
        choices=OPERATION_CHOICES,
    )
    challenge = models.BinaryField(
        help_text="Raw server-generated challenge bytes.",
    )
    expires_at = models.DateTimeField(
        db_index=True,
        help_text="Challenge expiry timestamp (typically 5 minutes from now).",
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["operation_type", "expires_at"],
                name="pkch_op_expires_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"PasskeyChallenge<{self.operation_type} expires={self.expires_at.isoformat()}>"


class ScheduledTaskRun(models.Model):
    """One row per scheduled task firing — both planned and recovered.

    Used by `apps.core.services.schedule_tracker` to remember when each
    registered schedule was supposed to run, when it actually did, and
    whether it succeeded. The unique-together on (task_name, scheduled_for)
    makes recovery sweeps idempotent: a missed slot can be re-fired without
    creating duplicate rows.

    The "sentient schedules" recovery loop reads this table on Django
    startup and every 10 min thereafter. If a slot in the recovery
    window has no row (or has `status='pending'` with `started_at IS NULL`),
    the loop fires the registered callable and marks the row recovered.

    Storage stays bounded because each schedule's `max_lookback_hours`
    caps how many missed slots can ever be replayed (default 72h).
    """

    STATUS_CHOICES = [
        ("pending", "pending"),
        ("running", "running"),
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("skipped", "skipped"),
    ]

    task_name = models.CharField(max_length=200, db_index=True)
    scheduled_for = models.DateTimeField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    last_error = models.TextField(blank=True, default="")
    recovered_run = models.BooleanField(
        default=False,
        help_text="True if this run was fired by the missed-schedule recovery sweep.",
    )
    payload = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Scheduled task run"
        verbose_name_plural = "Scheduled task runs"
        indexes = [
            models.Index(
                fields=["task_name", "-scheduled_for"], name="strun_task_recent_idx"
            ),
            models.Index(fields=["status"], name="strun_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["task_name", "scheduled_for"],
                name="strun_unique_task_per_slot",
            ),
        ]

    def __str__(self) -> str:
        recovered = " [recovered]" if self.recovered_run else ""
        return f"ScheduledTaskRun<{self.task_name} @ {self.scheduled_for.isoformat()} {self.status}{recovered}>"
