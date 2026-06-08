"""Auto-Issues — single store for issues surfaced by automated sources.

The C++ daily-picker (spec: ``docs/CPP-DAILY-ISSUE-PICKER-SPEC.md``) writes
into this table. Every agent reads ``status='open'`` rows at session start
via ``manage.py print_open_issues``.

Sources:
- ``glitchtip``  — backend / frontend exceptions captured via Sentry SDK.
- ``pyroscope``  — hot Python functions: regressions (week-over-week)
                  AND same-day hotspots (added 2026-05-10).
- ``tempo``      — distributed-trace findings: slow spans (duration over
                  threshold) AND error spans (status=error), grouped by
                  ``(span_name, service)`` (added 2026-05-11).
- ``loki``       — repeated WARN/ERROR patterns mined from container
                  stdout via LogQL (added 2026-05-10).
- ``faro``       — frontend RUM: JS error clusters AND Web Vitals
                  breaches (LCP / INP / CLS), shipped from Faro Web SDK
                  through Alloy into Loki (added 2026-05-11).
- ``agent``      — bugs found by an AI session that don't yet have a GT
                  issue (e.g. dead code, missing validation, smells).

Status flow: ``open`` → ``picked`` (an agent committed to fix) →
``fixing`` → ``resolved`` (or ``deferred`` with a written reason).
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class AutoIssueCategory(models.Model):
    """Extensible category taxonomy for AutoIssue rows."""

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Stable machine key, for example security or performance.",
    )
    label = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_issues_autoissuecategory"
        ordering = ["sort_order", "label"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
            models.Index(fields=["parent", "sort_order"]),
        ]

    def __str__(self) -> str:
        return str(self.label)


class AutoIssue(models.Model):
    SOURCE_GLITCHTIP = "glitchtip"
    SOURCE_PYROSCOPE = "pyroscope"
    SOURCE_TEMPO = "tempo"
    SOURCE_LOKI = "loki"
    SOURCE_FARO = "faro"
    SOURCE_SONARQUBE = "sonarqube"
    SOURCE_VMALERT = "vmalert"
    SOURCE_RUST_DEFECT = "rust_defect"
    SOURCE_PPROF = "pprof"
    SOURCE_ALLOY = "alloy"
    SOURCE_PERFETTO = "perfetto"
    SOURCE_GWP_ASAN = "gwp_asan"
    SOURCE_PROMETHEUS = "prometheus"
    SOURCE_PG_STAT = "pg_stat"
    SOURCE_LIGHTHOUSE = "lighthouse"
    SOURCE_TEST_FAILURE = "test_failure"
    SOURCE_AGENT = "agent"
    # Phase 6 of the test-hardening plan (added 2026-05-12):
    SOURCE_MUTATION = "mutation"     # mutmut / Stryker / Mull surviving mutants
    SOURCE_FUZZ = "fuzz"             # libFuzzer crashes / coverage gaps
    SOURCE_CONTRACT = "contract"     # Pact provider-verification drift
    SOURCE_GH_CI = "gh_ci"           # gh run list --status failure
    # Phase B of the test-hardening plan (added 2026-06-01):
    SOURCE_COMPILER = "compiler"     # clang/gcc/go vet/golangci-lint/clippy/GHC/hlint warnings
    SOURCE_MEGALINTER = "megalinter"  # MegaLinter multi-linter suite findings
    SOURCE_CHOICES = [
        (SOURCE_GLITCHTIP, "GlitchTip"),
        (SOURCE_PYROSCOPE, "Pyroscope"),
        (SOURCE_TEMPO, "Tempo"),
        (SOURCE_LOKI, "Loki"),
        (SOURCE_FARO, "Faro"),
        (SOURCE_SONARQUBE, "SonarQube"),
        (SOURCE_VMALERT, "vmalert"),
        (SOURCE_RUST_DEFECT, "Rust defect"),
        (SOURCE_PPROF, "pprof"),
        (SOURCE_ALLOY, "Alloy"),
        (SOURCE_PERFETTO, "Perfetto"),
        (SOURCE_GWP_ASAN, "GWP-ASan"),
        (SOURCE_PROMETHEUS, "Prometheus"),
        (SOURCE_PG_STAT, "pg_stat"),
        (SOURCE_LIGHTHOUSE, "Lighthouse"),
        (SOURCE_TEST_FAILURE, "Test failure"),
        (SOURCE_AGENT, "Agent find"),
        (SOURCE_MUTATION, "Mutation testing"),
        (SOURCE_FUZZ, "Fuzz testing"),
        (SOURCE_CONTRACT, "Contract drift"),
        (SOURCE_GH_CI, "GH Actions CI failure"),
        (SOURCE_COMPILER, "Compiler/linter warning"),
        (SOURCE_MEGALINTER, "MegaLinter"),
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
        blank=True,
        default="",
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
    concept_tags = ArrayField(
        models.CharField(max_length=64),
        default=list,
        blank=True,
        db_index=True,
        help_text="Approved concept tags used to find lessons across repo paths.",
    )
    artifact_refs = models.JSONField(
        blank=True,
        default=list,
        help_text="References to evidence blobs in the Mint blob store. No body content — SHA-256 + path only.",
    )

    title = models.CharField(max_length=512)
    description = models.TextField(blank=True)
    affected_files = models.JSONField(
        default=list,
        blank=True,
        help_text="List of repo-relative file paths the fix is likely to touch. Used by agents to decide if their work overlaps.",
    )
    category = models.ForeignKey(
        AutoIssueCategory,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="issues",
    )

    severity = models.CharField(
        max_length=12, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True
    )
    priority_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Set by the daily picker (spec: docs/CPP-DAILY-ISSUE-PICKER-SPEC.md). Higher = more important. Used to surface the top 10 each day.",
    )
    spam_score = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=(
            "Bayesian spam score in [0, 1] from `extensions.autoissue_spam_filter` "
            "(Sahami et al. 1998). 0=definitely ham, 1=definitely spam. NULL "
            "until first classification. Score-only — never auto-changes status; "
            "session-start pickers sort by (priority_score - spam_score) so noisy "
            "rows surface last. Rule H, added 2026-05-15."
        ),
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
            models.Index(fields=["category", "status"]),
            models.Index(fields=["canonical_fingerprint", "status"]),
        ]
        ordering = ["-priority_score", "-last_seen"]

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_RESOLVED and self.resolved_at is None:
            self.resolved_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "resolved_at" not in update_fields:
                kwargs["update_fields"] = list(update_fields) + ["resolved_at"]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        prefix = f"[{self.source}/{self.severity}] "
        budget = 100 - len(prefix)
        return f"{prefix}{str(self.title)[:budget]}"


class CodeQLFindingEvidence(models.Model):
    """Deduped LZ4-compressed evidence for one CodeQL finding."""

    issue = models.OneToOneField(
        AutoIssue,
        on_delete=models.CASCADE,
        related_name="codeql_evidence",
    )
    finding_fingerprint = models.CharField(max_length=64, unique=True)
    language = models.CharField(max_length=32, db_index=True)
    rule_id = models.CharField(max_length=128)
    file_path = models.TextField()
    line = models.PositiveIntegerField(default=1)
    compression = models.CharField(max_length=16, default="lz4")
    compressed_payload = models.BinaryField()
    uncompressed_bytes = models.PositiveIntegerField(default=0)
    compressed_bytes = models.PositiveIntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_issues_codeqlfindingevidence"
        indexes = [
            models.Index(fields=["language", "rule_id"]),
            models.Index(fields=["file_path"]),
        ]
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"[codeql/{self.language}] {self.rule_id} {self.file_path}:{self.line}"


class BuildFailureEvidence(models.Model):
    """Deduped LZ4-compressed terminal evidence for one compiler failure."""

    issue = models.OneToOneField(
        AutoIssue,
        on_delete=models.CASCADE,
        related_name="build_failure_evidence",
    )
    failure_fingerprint = models.CharField(max_length=64, unique=True)
    builder = models.CharField(max_length=64, db_index=True)
    targets = models.JSONField(default=list, blank=True)
    command = models.JSONField(default=list, blank=True)
    exit_code = models.PositiveIntegerField(default=1)
    compression = models.CharField(max_length=16, default="lz4")
    compressed_payload = models.BinaryField()
    uncompressed_bytes = models.PositiveIntegerField(default=0)
    compressed_bytes = models.PositiveIntegerField(default=0)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_issues_buildfailureevidence"
        indexes = [
            models.Index(fields=["builder", "-last_seen"]),
            models.Index(fields=["exit_code", "-last_seen"]),
        ]
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        target = ",".join(self.targets or ["<all>"])
        return f"[build/{self.builder}] {target} exit={self.exit_code}"


class FindBugsLearnedLesson(models.Model):
    """Deduped compressed lessons from FindBugs false calls and missed calls."""

    CLASS_FALSE_POSITIVE = "false_positive"
    CLASS_FALSE_NEGATIVE = "false_negative"
    CLASS_CHOICES = [
        (CLASS_FALSE_POSITIVE, "False positive"),
        (CLASS_FALSE_NEGATIVE, "False negative"),
    ]

    source_issue = models.ForeignKey(
        AutoIssue,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="findbugs_lessons",
    )
    classification = models.CharField(max_length=20, choices=CLASS_CHOICES, db_index=True)
    lesson_fingerprint = models.CharField(max_length=64, unique=True)
    compressed_payload = models.BinaryField()
    uncompressed_bytes = models.PositiveIntegerField(default=0)
    compressed_bytes = models.PositiveIntegerField(default=0)
    occurrence_count = models.PositiveIntegerField(default=1)
    approved = models.BooleanField(default=False)
    created_by = models.CharField(max_length=64, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_issues_findbugslearnedlesson"
        indexes = [
            models.Index(fields=["classification", "-last_seen"]),
            models.Index(fields=["approved", "-last_seen"]),
        ]
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"[findbugs-lesson/{self.classification}] {str(self.lesson_fingerprint)[:12]}"


class QualityEvidence(models.Model):
    """Compact, deduped evidence from tests and quality tools."""

    CHECK_NORMAL_TEST = "normal_test"
    CHECK_COVERAGE = "coverage"
    CHECK_MUTATION = "mutation"
    CHECK_STATIC_ANALYSIS = "static_analysis"
    CHECK_SECURITY = "security"
    CHECK_FUZZ = "fuzz"
    CHECK_SANITIZER = "sanitizer"
    CHECK_TOOL_READINESS = "tool_readiness"
    CHECK_MISSING_REPORT = "missing_report"
    CHECK_CI = "ci"
    CHECK_CHOICES = [
        (CHECK_NORMAL_TEST, "Normal test"),
        (CHECK_COVERAGE, "Coverage"),
        (CHECK_MUTATION, "Mutation"),
        (CHECK_STATIC_ANALYSIS, "Static analysis"),
        (CHECK_SECURITY, "Security"),
        (CHECK_FUZZ, "Fuzz"),
        (CHECK_SANITIZER, "Sanitizer"),
        (CHECK_TOOL_READINESS, "Tool readiness"),
        (CHECK_MISSING_REPORT, "Missing report"),
        (CHECK_CI, "CI"),
    ]

    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PASSED, "Passed"),
        (STATUS_FAILED, "Failed"),
    ]

    dedupe_key = models.CharField(
        max_length=64,
        unique=True,
        help_text=(
            "SHA-256 over check type, command, tool version, source hash, "
            "file path, and failure fingerprint."
        ),
    )
    check_type = models.CharField(max_length=32, choices=CHECK_CHOICES, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, db_index=True)
    tool_name = models.CharField(max_length=64)
    tool_version = models.CharField(max_length=128, blank=True)
    command = models.TextField()
    source_hash = models.CharField(max_length=64, db_index=True)
    file_path = models.CharField(max_length=512, blank=True, db_index=True)
    failure_fingerprint = models.CharField(max_length=128, blank=True, db_index=True)
    target_percent = models.FloatField(null=True, blank=True)
    actual_percent = models.FloatField(null=True, blank=True)
    summary = models.TextField(
        help_text="Plain-English compact summary. Service rejects values over 600 words.",
    )
    details = models.JSONField(default=dict, blank=True)
    raw_report_hash = models.CharField(max_length=64, blank=True)
    raw_snippet = models.ForeignKey(
        "QualityRawSnippet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quality_evidence",
    )
    auto_issue = models.ForeignKey(
        AutoIssue,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quality_evidence",
    )
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Retention marker used by quality evidence cleanup.",
    )

    class Meta:
        db_table = "auto_issues_qualityevidence"
        indexes = [
            models.Index(fields=["check_type", "status", "-last_seen"]),
            models.Index(fields=["source_hash", "failure_fingerprint"]),
            models.Index(fields=["expires_at", "status"]),
        ]
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"[{self.check_type}/{self.status}] {self.tool_name}: {self.file_path}"


class QualityRawSnippet(models.Model):
    """Deduped compressed raw snippet for weekly quality snapshots."""

    raw_report_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 over the capped raw snippet bytes.",
    )
    raw_report_gzip = models.BinaryField()
    uncompressed_bytes = models.PositiveIntegerField(default=0)
    compressed_bytes = models.PositiveIntegerField(default=0)
    reference_count = models.PositiveIntegerField(default=1)
    first_captured_week_start = models.DateField(db_index=True)
    last_captured_week_start = models.DateField(db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_issues_qualityrawsnippet"
        indexes = [
            models.Index(fields=["-last_captured_week_start", "-last_seen"]),
        ]
        ordering = ["-last_captured_week_start", "-last_seen"]

    def __str__(self) -> str:
        return f"[quality-raw] {str(self.raw_report_hash)[:12]}"
