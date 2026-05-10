"""Auto-Issues — single store for issues surfaced by automated sources.

The C++ daily-picker (spec: ``docs/CPP-DAILY-ISSUE-PICKER-SPEC.md``) writes
into this table. Every agent reads ``status='open'`` rows at session start
via ``manage.py print_open_issues``.

Sources:
- ``glitchtip``  — backend / frontend exceptions captured via Sentry SDK.
- ``pyroscope``  — hot Python functions: regressions (week-over-week)
                  AND same-day hotspots (added 2026-05-10).
- ``loki``       — repeated WARN/ERROR patterns mined from container
                  stdout via LogQL (added 2026-05-10).
- ``agent``      — bugs found by an AI session that don't yet have a GT
                  issue (e.g. dead code, missing validation, smells).

Status flow: ``open`` → ``picked`` (an agent committed to fix) →
``fixing`` → ``resolved`` (or ``deferred`` with a written reason).
"""

from __future__ import annotations

from django.db import models


class AutoIssue(models.Model):
    SOURCE_GLITCHTIP = "glitchtip"
    SOURCE_PYROSCOPE = "pyroscope"
    SOURCE_LOKI = "loki"
    SOURCE_AGENT = "agent"
    SOURCE_CHOICES = [
        (SOURCE_GLITCHTIP, "GlitchTip"),
        (SOURCE_PYROSCOPE, "Pyroscope"),
        (SOURCE_LOKI, "Loki"),
        (SOURCE_AGENT, "Agent find"),
    ]

    STATUS_OPEN = "open"
    STATUS_PICKED = "picked"
    STATUS_FIXING = "fixing"
    STATUS_RESOLVED = "resolved"
    STATUS_DEFERRED = "deferred"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_PICKED, "Picked"),
        (STATUS_FIXING, "Fixing"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DEFERRED, "Deferred"),
    ]

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

    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, db_index=True)
    external_id = models.CharField(
        max_length=128,
        help_text="Source-specific id: GlitchTip issue id OR Pyroscope function fingerprint OR free-form string for agent finds.",
    )
    fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Source-specific fingerprint. Differs across sources (GT, internal, Pyroscope each compute their own).",
    )
    # Source-agnostic dedup key. When the same root cause is captured by
    # GlitchTip (Sentry SDK) AND by an internal `ingest_error()` call AND
    # by Pyroscope (regression detection), all three rows have the same
    # `canonical_fingerprint` so an agent reading the auto_issues list
    # sees ONE entry per root cause, not three. Computed by
    # `services.fingerprinting.canonical_fingerprint(title, culprit)`.
    canonical_fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        default="",
        help_text="Cross-source dedup key. Same value across sources for the same root cause.",
    )
    # When canonical_fingerprint matches an existing row, the picker
    # appends an entry here instead of creating a new row. Each entry:
    # {"source": "glitchtip", "external_id": "gt-123", "first_seen": ISO,
    #  "last_seen": ISO, "occurrence_count": int}.
    source_observations = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {source, external_id, first_seen, last_seen, occurrence_count} entries — one per source that has observed this root cause.",
    )

    title = models.CharField(max_length=512)
    description = models.TextField(blank=True)
    affected_files = models.JSONField(
        default=list,
        blank=True,
        help_text="List of repo-relative file paths the fix is likely to touch. Used by agents to decide if their work overlaps.",
    )

    severity = models.CharField(
        max_length=12, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True
    )
    priority_score = models.FloatField(
        default=0.0,
        help_text="Set by the daily picker (spec: docs/CPP-DAILY-ISSUE-PICKER-SPEC.md). Higher = more important. Used to surface the top 10 each day.",
    )

    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(
        max_length=64,
        blank=True,
        help_text="Agent name (claude, codex, gemini) or human username that closed the issue.",
    )
    fix_commit_sha = models.CharField(max_length=64, blank=True)

    # When status='resolved', the agent that fixed it writes a short
    # plain-English note here describing what NOT to do next time AND
    # what the fix actually was. Read by `search_resolved_issues` at
    # session start so future agents avoid the same trap. Indexed by
    # `affected_files` (JSONField) plus this column being non-empty —
    # the search is "did anyone fix something in <file_x> before? what
    # did they learn?"
    lessons_learned = models.TextField(
        blank=True,
        help_text=(
            "Plain-English note from the resolving agent. Two parts: "
            "(1) the trap (what's NOT obvious about this code area), "
            "(2) the fix shape (what worked). Read by future agents "
            "via `manage.py search_resolved_issues --area <path>`."
        ),
    )

    class Meta:
        db_table = "auto_issues_autoissue"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="uniq_autoissue_source_external_id",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-priority_score"]),
            models.Index(fields=["source", "status"]),
            models.Index(fields=["canonical_fingerprint", "status"]),
        ]
        ordering = ["-priority_score", "-last_seen"]

    def __str__(self) -> str:
        return f"[{self.source}/{self.severity}] {self.title[:60]}"
