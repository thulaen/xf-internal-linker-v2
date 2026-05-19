"""PaperTrailEntry — database-backed deferred-work tracker.

One row per deferred work item. Schema is parallel to AutoIssue but
does NOT overlap: AutoIssue tracks discovered problems; paper trail
tracks deliberately-deferred work, with a detailed abstract explaining
why, plus dedup via the C++ MinHash + LSH index in
`backend/extensions/papertrail_dedup.cpp`.

The save() override enforces:
- abstract ≤ 600 words
- status=resolved requires two-part 'Trap: ... Fix shape: ...' lesson
- status=wontfix requires suppression_reason
- fingerprint + canonical_fingerprint auto-computed on first save
- history JSON receives an audit entry on creation and on status change
"""

from __future__ import annotations

import hashlib
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


_NORMALISE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    (re.compile(r"\b\d{4,}\b"), "<n>"),
)


def _normalise(text: str) -> str:
    out = text.lower().strip()
    for pat, repl in _NORMALISE_PATTERNS:
        out = pat.sub(repl, out)
    return re.sub(r"\s+", " ", out)


def _short_sha1(text: str) -> str:
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:16]


class PaperTrailEntry(models.Model):
    """A single deferred-work entry with a detailed abstract."""

    # ── Status choices ────────────────────────────────────────────
    STATUS_OPEN = "open"
    STATUS_PICKED = "picked"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_BLOCKED = "blocked"           # 2026-05-16: external blocker
    STATUS_DEFERRED = "deferred"         # 2026-05-16: reviewed + pushed forward
    STATUS_RESOLVED = "resolved"
    STATUS_WONTFIX = "wontfix"           # legacy alias of REJECTED
    STATUS_REJECTED = "rejected"         # 2026-05-16: approach rejected
    STATUS_DUPLICATE = "duplicate"
    STATUS_STALE = "stale"               # 2026-05-16: no longer relevant
    STATUS_SUPERSEDED = "superseded"     # 2026-05-16: replaced by another entry
    STATUS_CHOICES = (
        (STATUS_OPEN, "Open"),
        (STATUS_PICKED, "Picked"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_DEFERRED, "Deferred"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_WONTFIX, "Wontfix"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_DUPLICATE, "Duplicate"),
        (STATUS_STALE, "Stale"),
        (STATUS_SUPERSEDED, "Superseded"),
    )
    _ACTIVE_STATUSES = (
        STATUS_OPEN,
        STATUS_PICKED,
        STATUS_IN_PROGRESS,
        STATUS_BLOCKED,
        STATUS_DEFERRED,
    )
    _TERMINAL_STATUSES = (
        STATUS_RESOLVED,
        STATUS_WONTFIX,
        STATUS_REJECTED,
        STATUS_DUPLICATE,
        STATUS_STALE,
        STATUS_SUPERSEDED,
    )

    # ── Severity choices ──────────────────────────────────────────
    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_CHOICES = (
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_LOW, "Low"),
    )

    # ── Category choices (16) ─────────────────────────────────────
    CATEGORY_AUTOISSUE_DEFERRAL = "autoissue_deferral"
    CATEGORY_CVE_UPGRADE = "cve_upgrade"
    CATEGORY_COVERAGE_GAP = "coverage_gap"
    CATEGORY_INFRASTRUCTURE = "infrastructure"
    CATEGORY_RUFF_SWEEP = "ruff_sweep"
    CATEGORY_MUTATION_SURVIVOR = "mutation_survivor"
    CATEGORY_DEBT_REDUCTION = "debt_reduction"
    CATEGORY_FEATURE_DECISION = "feature_decision"
    CATEGORY_TOOLING_GAP = "tooling_gap"
    CATEGORY_DOCUMENTATION = "documentation"
    CATEGORY_DEPENDENCY_UPGRADE = "dependency_upgrade"
    CATEGORY_REFACTOR = "refactor"
    CATEGORY_PERFORMANCE = "performance"
    CATEGORY_SECURITY = "security"
    CATEGORY_ACCESSIBILITY = "accessibility"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = (
        (CATEGORY_AUTOISSUE_DEFERRAL, "AutoIssue deferral"),
        (CATEGORY_CVE_UPGRADE, "CVE upgrade"),
        (CATEGORY_COVERAGE_GAP, "Coverage gap"),
        (CATEGORY_INFRASTRUCTURE, "Infrastructure"),
        (CATEGORY_RUFF_SWEEP, "Ruff sweep"),
        (CATEGORY_MUTATION_SURVIVOR, "Mutation survivor"),
        (CATEGORY_DEBT_REDUCTION, "Debt reduction"),
        (CATEGORY_FEATURE_DECISION, "Feature decision"),
        (CATEGORY_TOOLING_GAP, "Tooling gap"),
        (CATEGORY_DOCUMENTATION, "Documentation"),
        (CATEGORY_DEPENDENCY_UPGRADE, "Dependency upgrade"),
        (CATEGORY_REFACTOR, "Refactor"),
        (CATEGORY_PERFORMANCE, "Performance"),
        (CATEGORY_SECURITY, "Security"),
        (CATEGORY_ACCESSIBILITY, "Accessibility"),
        (CATEGORY_OTHER, "Other"),
    )

    # ── Visibility ────────────────────────────────────────────────
    VISIBILITY_PUBLIC = "public"
    VISIBILITY_INTERNAL = "internal"
    VISIBILITY_CHOICES = (
        (VISIBILITY_PUBLIC, "Public"),
        (VISIBILITY_INTERNAL, "Internal"),
    )

    # ── Complexity bucket ─────────────────────────────────────────
    COMPLEXITY_CHOICES = (
        ("XS", "XS"),
        ("S", "S"),
        ("M", "M"),
        ("L", "L"),
        ("XL", "XL"),
    )

    # ── Evidence level (2026-05-16) ───────────────────────────────
    # Tracks how well-grounded the deferral's claims are. `cited` means
    # the entry references a patent / DOI / RFC / stable URL; `high`
    # means it cites concrete artifacts (file paths, function names,
    # test failures); `medium` means it cites observable behavior;
    # `low` is the default (subjective or anecdotal).
    EVIDENCE_LOW = "low"
    EVIDENCE_MEDIUM = "medium"
    EVIDENCE_HIGH = "high"
    EVIDENCE_CITED = "cited"
    EVIDENCE_CHOICES = (
        (EVIDENCE_LOW, "Low"),
        (EVIDENCE_MEDIUM, "Medium"),
        (EVIDENCE_HIGH, "High"),
        (EVIDENCE_CITED, "Cited (patent / DOI / RFC / URL)"),
    )

    # ── Identity & dedup ──────────────────────────────────────────
    id = models.AutoField(primary_key=True)
    fingerprint = models.CharField(
        max_length=16,
        db_index=True,
        blank=True,
        default="",
        help_text="SHA1-16 of (category, normalised title, linked_autoissue_id). Exact-match dedup.",
    )
    canonical_fingerprint = models.CharField(
        max_length=16,
        db_index=True,
        blank=True,
        default="",
        help_text="SHA1-16 of normalised title alone. Cross-content dedup key for fast SQL filtering.",
    )

    # ── Classification ────────────────────────────────────────────
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES, db_index=True)
    severity = models.CharField(max_length=12, choices=SEVERITY_CHOICES, default=SEVERITY_MEDIUM)

    # ── Content ───────────────────────────────────────────────────
    title = models.CharField(max_length=512)
    abstract = models.TextField(
        max_length=9500,
        help_text=(
            "High-detail explanation of why this work was deferred. "
            "Hard-capped at 1200 words. NEW entries (2026-05-16 onward) "
            "MUST be written in BDD style: contain a `Given ...`, `When ...`, "
            "and `Then ...` section so the deferral has a self-contained "
            "test-shape that the next agent can read as an acceptance spec. "
            "Existing pre-2026-05-16 abstracts are grandfathered."
        ),
    )
    next_actions = models.JSONField(default=list, blank=True)
    affected_files = models.JSONField(default=list, blank=True)

    # ── Lifecycle ─────────────────────────────────────────────────
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    deferred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deferred_by = models.CharField(max_length=64)
    deferred_in_handoff = models.CharField(max_length=24, blank=True, default="")
    deferral_reason_key = models.CharField(max_length=32, blank=True, default="")

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=64, blank=True, default="")
    resolution_lessons = models.TextField(blank=True, default="")
    resolution_commit_sha = models.CharField(max_length=40, blank=True, default="")

    # ── Re-detection ──────────────────────────────────────────────
    last_seen = models.DateTimeField(auto_now=True, db_index=True)
    occurrence_count = models.PositiveIntegerField(default=1)

    # ── Linkage ───────────────────────────────────────────────────
    linked_autoissue_id = models.IntegerField(null=True, blank=True, db_index=True)
    linked_registry_id = models.CharField(max_length=24, blank=True, default="")
    linked_commit_sha = models.CharField(max_length=40, blank=True, default="")

    # ── Priority + estimation ─────────────────────────────────────
    priority_score = models.FloatField(default=0.0, db_index=True)
    estimated_hours = models.FloatField(default=0.0)
    complexity_bucket = models.CharField(max_length=4, choices=COMPLEXITY_CHOICES, default="M")

    # ── Optional context fields (subset of the 25 gap ideas) ──────
    blockers = models.JSONField(default=list, blank=True)
    required_skills = models.JSONField(default=list, blank=True)
    resource_needs = models.JSONField(default=list, blank=True)
    risk_on_inaction = models.TextField(blank=True, default="")
    confidence = models.FloatField(default=0.5)
    resolution_criteria = models.TextField(blank=True, default="")
    related_entry_ids = models.JSONField(default=list, blank=True)
    citations = models.JSONField(default=list, blank=True)
    visibility = models.CharField(max_length=12, choices=VISIBILITY_CHOICES, default=VISIBILITY_INTERNAL)
    suppression_reason = models.TextField(blank=True, default="")
    suppression_approver = models.CharField(max_length=64, blank=True, default="")
    history = models.JSONField(default=list, blank=True)

    # ── Required-on-new fields (2026-05-16) ───────────────────────
    # These are blank=True+default="" at the schema layer so the
    # migration can apply without backfilling existing rows. The
    # _validate() method requires them on new rows only via the
    # self._state.adding guard (same grandfathering pattern as BDD).
    acceptance_criteria = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Bullet list or short paragraph naming the concrete checks "
            "that prove this entry can be marked resolved. Required on "
            "all NEW entries (2026-05-16+); existing rows grandfathered."
        ),
    )
    evidence_level = models.CharField(
        max_length=10,
        choices=EVIDENCE_CHOICES,
        default=EVIDENCE_LOW,
        db_index=True,
        help_text=(
            "How well-grounded the entry's claims are. `cited` requires "
            "a patent / DOI / RFC / stable URL in the abstract."
        ),
    )
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
        help_text=(
            "Newer entry that replaces this one. Set via "
            "manage.py link_paper_trail_supersedes."
        ),
    )
    integrity_check_result = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Result of the duplicate / stale / conflict search the "
            "filing agent performed before creating this entry. Auto-"
            "populated by manage.py defer_work."
        ),
    )

    # ── Paper Trail Evidence Rule (2026-05-17) ────────────────────
    # PK of the AutoIssue(category='test_case') row whose lessons_learned
    # carries the full 10-field BDD contract (Given/When/Then + 7 extended
    # fields). Required on entries deferred_at >= 2026-05-17. Pre-cutoff
    # entries grandfathered via _state.adding + deferred_at comparison.
    test_case_autoissue_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "PK of the AutoIssue(category='test_case') row whose "
            "lessons_learned carries the full 10-field BDD contract "
            "for this entry. Required on entries deferred_at >= "
            "2026-05-17 per docs/PAPER-TRAIL-EVIDENCE-RULE.md."
        ),
    )

    class Meta:
        constraints = [
            # Active statuses (open, picked, in_progress, blocked, deferred)
            # must not have duplicate (category, fingerprint) pairs.
            # Terminal statuses (resolved, wontfix, rejected, duplicate,
            # stale, superseded) are exempt so a new entry can replace a
            # closed one with the same fingerprint.
            models.UniqueConstraint(
                fields=["category", "fingerprint"],
                condition=Q(status__in=("open", "picked", "in_progress", "blocked", "deferred")),
                name="uniq_papertrail_active_category_fingerprint",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "severity", "category"]),
            models.Index(fields=["canonical_fingerprint"]),
            models.Index(fields=["deferred_at"]),
            models.Index(fields=["linked_autoissue_id"]),
            models.Index(fields=["priority_score"]),
            models.Index(fields=["last_seen"]),
        ]

    # ── Public API ────────────────────────────────────────────────
    def __str__(self) -> str:
        title = str(self.title or "")
        return f"PaperTrail #{self.pk} [{self.category}/{self.severity}] {title[:60]}"

    def compute_fingerprints(self) -> tuple[str, str]:
        """Compute (fingerprint, canonical_fingerprint) without saving."""
        title = str(self.title or "")
        canonical_source = _normalise(title)
        canonical = _short_sha1(canonical_source)
        link_key = "" if self.linked_autoissue_id is None else str(self.linked_autoissue_id)
        exact_source = f"{self.category}|{canonical_source}|{link_key}"
        exact = _short_sha1(exact_source)
        return exact, canonical

    def _word_count(self) -> int:
        return len(self.abstract.split())

    def _validate(self) -> None:
        if self._word_count() > 1200:
            raise ValidationError(
                "abstract exceeds 1200 words "
                f"(got {self._word_count()}). Trim the abstract first; "
                "move long-form detail into a docs/specs/ file."
            )
        # BDD-format requirement applies to NEW rows only. Existing rows
        # being status-changed or re-saved keep their grandfathered text.
        if self._state.adding and self._missing_bdd_parts():
            missing = self._missing_bdd_parts()
            raise ValidationError(
                f"abstract is missing required BDD section(s): {', '.join(missing)}. "
                "Every NEW paper-trail abstract MUST be in BDD style with "
                "`Given <context>`, `When <action>`, and `Then <expected outcome>` "
                "sections so the next agent reads the deferral as a self-"
                "contained acceptance spec."
            )
        # Required-on-new fields (2026-05-16). Existing rows grandfathered.
        if self._state.adding:
            missing_required: list[str] = []
            if not (self.risk_on_inaction or "").strip():
                missing_required.append("risk_on_inaction")
            if not (self.acceptance_criteria or "").strip():
                missing_required.append("acceptance_criteria")
            if missing_required:
                raise ValidationError(
                    "NEW paper-trail entries MUST populate: "
                    + ", ".join(missing_required)
                    + ". Use manage.py defer_work with --risk-on-inaction "
                    "and --acceptance-criteria so the next agent knows "
                    "what breaks if this is ignored and what 'done' looks "
                    "like."
                )
        # Paper Trail Evidence Rule (2026-05-17). Applies to all NEW rows
        # filed on or after the cutoff. The model layer enforces presence;
        # the detailed regex + test-case-completeness check lives in
        # manage.py defer_work + manage.py verify_paper_trail_evidence so
        # the error message can point at the specific failing input.
        if self._state.adding:
            evidence_problems: list[str] = []
            if self.test_case_autoissue_id is None:
                evidence_problems.append("test_case_autoissue_id (link to AutoIssue(category='test_case'))")
            if not (self.citations or []):
                evidence_problems.append("citations (>= 1 patent / DOI / arXiv / standard / RFC / ISBN / official URL)")
            if evidence_problems:
                raise ValidationError(
                    "NEW paper-trail entries from 2026-05-17 onward MUST carry: "
                    + ", ".join(evidence_problems)
                    + ". Use manage.py defer_work with --test-case-autoissue <N> "
                    "and --citation <id> (repeatable) per "
                    "docs/PAPER-TRAIL-EVIDENCE-RULE.md."
                )
        if self.status == self.STATUS_RESOLVED:
            lessons = str(self.resolution_lessons or "")
            if "Trap:" not in lessons or "Fix shape:" not in lessons:
                raise ValidationError(
                    "resolution_lessons must include both 'Trap:' and "
                    "'Fix shape:' parts when status=resolved."
                )
            if not self.resolved_at:
                raise ValidationError("resolved_at must be set when status=resolved.")
        if self.status in (self.STATUS_WONTFIX, self.STATUS_REJECTED) and not self.suppression_reason:
            raise ValidationError(
                "suppression_reason is required when status=wontfix or status=rejected."
            )
        if self.status == self.STATUS_BLOCKED and not (self.blockers or []):
            raise ValidationError(
                "blockers list is required when status=blocked. Use "
                "manage.py block_paper_trail --id <N> --blocker '...'."
            )
        if self.status == self.STATUS_STALE and not (self.suppression_reason or "").strip():
            raise ValidationError(
                "suppression_reason is required when status=stale "
                "(explain why this entry is no longer relevant)."
            )
        if self.status == self.STATUS_SUPERSEDED and self.superseded_by_id is None:
            raise ValidationError(
                "superseded_by must point to the replacement entry when "
                "status=superseded. Use manage.py link_paper_trail_supersedes."
            )

    def _missing_bdd_parts(self) -> list[str]:
        """Return the list of missing BDD section keywords (case-insensitive)."""
        text = (self.abstract or "").lower()
        missing: list[str] = []
        # Match `given`, `when`, `then` as standalone-ish words to avoid
        # false positives on substrings inside other words (e.g. "whenever").
        for keyword in ("given", "when", "then"):
            if not re.search(rf"\b{keyword}\b", text):
                missing.append(keyword.capitalize())
        return missing

    def _ensure_fingerprints(self) -> None:
        if not self.fingerprint or not self.canonical_fingerprint:
            self.fingerprint, self.canonical_fingerprint = self.compute_fingerprints()

    def _append_history(self, action: str, *, note: str = "") -> None:
        entry = {
            "at": timezone.now().isoformat(),
            "by": self.deferred_by if not self.resolved_by else self.resolved_by,
            "action": action,
        }
        if note:
            entry["note"] = note
        self.history = [*self.history, entry]

    def save(self, *args, **kwargs):
        self._ensure_fingerprints()
        self._validate()
        is_new = self._state.adding
        # Capture pre-save status for change detection on update.
        previous_status: str | None = None
        if not is_new:
            previous_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        if is_new:
            self._append_history("created")
        elif previous_status is not None and previous_status != self.status:
            self._append_history(f"status:{self.status}")
        super().save(*args, **kwargs)
