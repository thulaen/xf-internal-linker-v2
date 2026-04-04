"""
Suggestions models — pipeline runs, link suggestions, and diagnostics.

A Suggestion is the core output of the ML pipeline:
  destination ← host sentence (where the link will be placed)

The human reviewer approves or rejects each suggestion in the review UI.
The app NEVER writes to XenForo — the human manually applies approved suggestions.
"""

import uuid

from django.db import models

from apps.core.models import TimestampedModel


class WeightPreset(TimestampedModel):
    """
    A named snapshot of all ranking-weight AppSetting values (categories ml,
    link_freshness, anchor).

    System presets (is_system=True) are read-only — they cannot be edited or
    deleted via the API.  The "Recommended" preset is seeded by a data migration.

    The weights JSON is a flat key/value map keyed by AppSetting.key.  Any key
    absent from the JSON falls back to that signal's hardcoded default when the
    preset is applied.  This means adding a new signal in a future phase does NOT
    break existing presets.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Friendly name for this preset, e.g. 'Recommended' or 'Authority-heavy'.",
    )
    is_system = models.BooleanField(
        default=False,
        db_index=True,
        help_text="System presets are read-only and cannot be modified or deleted via the API.",
    )
    weights = models.JSONField(
        default=dict,
        help_text=(
            "Flat key/value map of AppSetting keys → values for all "
            "settings in categories ml, link_freshness, and anchor."
        ),
    )

    class Meta:
        verbose_name = "Weight Preset"
        verbose_name_plural = "Weight Presets"
        ordering = ["-is_system", "name"]

    def __str__(self) -> str:
        tag = " [system]" if self.is_system else ""
        return f"{self.name}{tag}"


class WeightAdjustmentHistory(models.Model):
    """
    Bulk audit record for every event that changes ranking weights.

    One row is written each time weights change — whether triggered by a preset
    apply, a manual settings save, or the monthly R auto-tune task.

    This is additive to AuditEntry: AuditEntry still fires per-key for every
    individual AppSetting.key that changes.  WeightAdjustmentHistory adds a
    single bulk event record on top of that per-key trail.
    """

    SOURCE_CHOICES = [
        ("r_auto", "Monthly R auto-tune"),
        ("cs_auto_tune", "C# L-BFGS auto-tune (FR-018)"),
        ("manual", "Manual save"),
        ("preset_applied", "Preset applied"),
    ]

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        db_index=True,
        help_text="What triggered this weight change.",
    )
    preset = models.ForeignKey(
        WeightPreset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjustment_history",
        help_text="The preset that was applied (only set when source='preset_applied').",
    )
    previous_weights = models.JSONField(
        default=dict,
        help_text="Snapshot of all in-scope weights before the change.",
    )
    new_weights = models.JSONField(
        default=dict,
        help_text="Snapshot of all in-scope weights after the change.",
    )
    delta = models.JSONField(
        default=dict,
        help_text="Only the keys that changed, with {previous, new} sub-keys.",
    )
    reason = models.CharField(
        max_length=500,
        help_text="Plain-English summary, e.g. 'Preset: Recommended applied by admin'.",
    )
    r_run_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="Reference to the R analytics run (populated by FR-018 when active).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this adjustment was recorded.",
    )

    class Meta:
        verbose_name = "Weight Adjustment"
        verbose_name_plural = "Weight Adjustment History"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.source}] {self.reason[:80]} at {self.created_at}"


class RankingChallenger(TimestampedModel):
    """
    A candidate weight set produced by the C# L-BFGS auto-tuner (FR-018).

    C# POSTs one RankingChallenger row per tune run via the internal write
    endpoint.  Django's evaluate_weight_challenger Celery task then scores it
    against the current champion (active AppSetting values) and either promotes
    it, rejects it, or leaves it pending for human review.

    Only the four core blend weights (w_semantic, w_keyword, w_node, w_quality)
    are tuned by the optimizer.  All other weights remain at their current values.
    """

    STATUS_CHOICES = [
        ("pending", "Pending evaluation"),
        ("promoted", "Promoted to champion"),
        ("rolled_back", "Rolled back after regression"),
        ("rejected", "Rejected — did not beat champion"),
    ]

    run_id = models.CharField(
        max_length=200,
        unique=True,
        help_text="Opaque identifier from the C# tune run (e.g. a GUID).",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="Lifecycle state of this challenger.",
    )
    candidate_weights = models.JSONField(
        default=dict,
        help_text=(
            "Flat key→value map of the four tunable weights proposed by the optimizer: "
            "w_semantic, w_keyword, w_node, w_quality."
        ),
    )
    baseline_weights = models.JSONField(
        default=dict,
        help_text="Snapshot of the four active weights at the moment C# submitted this challenger.",
    )
    predicted_quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Predicted link-quality score from the C# optimizer for the candidate weights.",
    )
    champion_quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Predicted link-quality score for the current champion weights (for comparison).",
    )
    history = models.OneToOneField(
        "WeightAdjustmentHistory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="challenger",
        help_text="The WeightAdjustmentHistory row written when this challenger was promoted.",
    )

    class Meta:
        verbose_name = "Ranking Challenger"
        verbose_name_plural = "Ranking Challengers"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Challenger {self.run_id[:16]} [{self.status}]"


class ScopePreset(TimestampedModel):
    """
    A saved named configuration of which scopes are included in a pipeline run.
    Users can save presets like "All Music Threads" or "Guitar + Bass Only".
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Friendly name for this preset, e.g. 'All Guitar Forums'.",
    )
    scope_mode = models.CharField(
        max_length=50,
        help_text="How the scope is applied: 'all', 'include', or 'exclude'.",
    )
    enabled_ids = models.JSONField(
        default=list,
        help_text="List of ScopeItem PKs included or excluded, depending on scope_mode.",
    )

    class Meta:
        verbose_name = "Scope Preset"
        verbose_name_plural = "Scope Presets"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PipelineRun(TimestampedModel):
    """
    Metadata for a single batch pipeline execution.

    Each run processes a set of destinations, finds host sentences,
    and creates Suggestion records. Celery task ID is stored so the frontend
    can subscribe to real-time progress via WebSocket.
    """

    RERUN_MODE_CHOICES = [
        ("skip_pending", "Skip Pending — don't replace existing pending suggestions"),
        ("supersede_pending", "Supersede Pending — replace with new suggestions"),
        ("full_regenerate", "Full Regenerate — replace all, including approved"),
    ]

    RUN_STATE_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    run_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this pipeline run.",
    )
    rerun_mode = models.CharField(
        max_length=30,
        choices=RERUN_MODE_CHOICES,
        default="skip_pending",
        help_text="Controls how this run handles destinations that already have suggestions.",
    )
    host_scope = models.JSONField(
        default=dict,
        help_text="Scope config for host content (which threads can have links inserted).",
    )
    destination_scope = models.JSONField(
        default=dict,
        help_text="Scope config for destination content (which threads are linked to).",
    )
    run_state = models.CharField(
        max_length=20,
        choices=RUN_STATE_CHOICES,
        default="queued",
        db_index=True,
        help_text="Current execution state of this pipeline run.",
    )
    suggestions_created = models.IntegerField(
        default=0,
        help_text="Number of new suggestions generated in this run.",
    )
    destinations_processed = models.IntegerField(
        default=0,
        help_text="Number of destination items fully processed.",
    )
    destinations_skipped = models.IntegerField(
        default=0,
        help_text="Number of destination items skipped (no good match found).",
    )
    duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Total wall-clock seconds the run took to complete.",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error details if run_state is 'failed'.",
    )
    config_snapshot = models.JSONField(
        default=dict,
        help_text="Frozen ML weights and settings at the time this run started.",
    )
    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Celery task ID — used by the frontend to subscribe to WebSocket progress.",
    )

    class Meta:
        verbose_name = "Pipeline Run"
        verbose_name_plural = "Pipeline Runs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Run {str(self.run_id)[:8]} — {self.run_state} "
            f"({self.suggestions_created} suggestions)"
        )


class Suggestion(TimestampedModel):
    """
    A single link suggestion: place a link to `destination` inside `host_sentence`.

    Status lifecycle:
      pending → approved → applied → verified
      pending → rejected
      approved/applied → stale  (host/destination edited or deleted)
      pending/approved → superseded  (newer pipeline run replaces it)
    """

    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("applied", "Applied"),
        ("verified", "Verified"),
        ("stale", "Stale"),
        ("superseded", "Superseded"),
    ]

    REJECTION_REASON_CHOICES = [
        ("", "— No reason —"),
        ("irrelevant", "Irrelevant / off-topic"),
        ("low_quality", "Low quality match"),
        ("already_linked", "Already linked"),
        ("bad_anchor", "Bad anchor text"),
        ("wrong_context", "Wrong context"),
        ("duplicate", "Duplicate suggestion"),
        ("other", "Other"),
    ]

    ANCHOR_CONFIDENCE_CHOICES = [
        ("strong", "Strong (exact phrase match)"),
        ("weak", "Weak (partial / fallback)"),
        ("none", "None (no anchor found)"),
    ]

    suggestion_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this suggestion.",
    )
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestions",
        help_text="The pipeline run that generated this suggestion.",
    )

    # Destination — the page being linked TO
    destination = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="destination_suggestions",
        help_text="The content item that will receive an incoming link.",
    )
    destination_title = models.CharField(
        max_length=500,
        blank=True,
        help_text="Denormalized destination title for fast display without JOINs.",
    )

    # Host — the page where the link will be PLACED
    host = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="host_suggestions",
        help_text="The content item whose post will contain the new link.",
    )
    host_sentence = models.ForeignKey(
        "content.Sentence",
        on_delete=models.CASCADE,
        related_name="suggestions",
        help_text="The specific sentence where the link will be inserted.",
    )
    host_sentence_text = models.TextField(
        blank=True,
        help_text="Denormalized sentence text for fast display without JOINs.",
    )

    # ML scores
    score_semantic = models.FloatField(
        default=0.0,
        help_text="Cosine similarity between destination embedding and host sentence embedding.",
    )
    score_keyword = models.FloatField(
        default=0.0,
        help_text="Keyword overlap score between destination distilled text and host sentence.",
    )
    score_node_affinity = models.FloatField(
        default=0.0,
        help_text="Bonus when destination and host are in related forum nodes.",
    )
    score_quality = models.FloatField(
        default=0.0,
        help_text="Quality score based on host thread engagement metrics.",
    )
    score_march_2026_pagerank = models.FloatField(
        "March 2026 PageRank",
        default=0.0,
        help_text="March 2026 PageRank of the destination (higher = more editorially prominent).",
    )
    score_velocity = models.FloatField(
        default=0.0,
        help_text="Velocity/recency bonus for trending destinations.",
    )
    score_link_freshness = models.FloatField(
        default=0.5,
        help_text="Link Freshness score of the destination. 0.5 means neutral or not enough history.",
    )
    score_phrase_relevance = models.FloatField(
        default=0.5,
        help_text="FR-008 phrase relevance score for this destination/host sentence pair. 0.5 means neutral.",
    )
    score_learned_anchor_corroboration = models.FloatField(
        default=0.5,
        help_text="FR-009 learned-anchor corroboration score for this destination/host sentence pair. 0.5 means neutral.",
    )
    score_rare_term_propagation = models.FloatField(
        default=0.5,
        help_text="FR-010 rare-term propagation score for this destination/host sentence pair. 0.5 means neutral.",
    )
    score_field_aware_relevance = models.FloatField(
        default=0.5,
        help_text="FR-011 field-aware relevance score for this destination/host sentence pair. 0.5 means neutral.",
    )
    score_ga4_gsc = models.FloatField(
        default=0.5,
        help_text="Stores the destination content-value score at suggestion-scoring time. 0.5 = neutral.",
    )
    score_click_distance = models.FloatField(
        default=0.5,
        help_text="FR-012 click-distance structural prior score. 1.0 = shallowest. 0.5 = neutral.",
    )
    score_explore_exploit = models.FloatField(
        default=0.5,
        help_text="FR-013 feedback-driven explore/exploit reranking score. 0.5 = neutral.",
    )
    score_cluster_suppression = models.FloatField(
        default=0.0,
        help_text="FR-014 near-duplicate clustering suppression score. Negative values indicate suppression.",
    )
    score_final = models.FloatField(
        default=0.0,
        db_index=True,
        help_text="Weighted composite of all score components. Used to rank suggestions.",
    )

    # FR-021 Graph and Value Model
    candidate_origin = models.CharField(
        max_length=20,
        choices=[
            ("embedding", "Embedding Similarity"),
            ("graph_walk", "Pixie Graph Walk"),
            ("both", "Both Channel Match"),
        ],
        default="embedding",
        db_index=True,
        help_text="Which candidate generation channel produced this suggestion.",
    )
    score_value_model = models.FloatField(
        null=True,
        blank=True,
        help_text="Pre-ranking score from the Instagram-style value model (relevance + traffic).",
    )
    value_model_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable signals and weights used in the Value Model pass.",
    )

    # Anchor text
    anchor_phrase = models.CharField(
        max_length=500,
        blank=True,
        help_text="The phrase in the host sentence that becomes the clickable link text.",
    )
    anchor_start = models.IntegerField(
        null=True,
        blank=True,
        help_text="Character offset of anchor_phrase within host_sentence_text.",
    )
    anchor_end = models.IntegerField(
        null=True,
        blank=True,
        help_text="Character end offset of anchor_phrase within host_sentence_text.",
    )
    anchor_confidence = models.CharField(
        max_length=20,
        choices=ANCHOR_CONFIDENCE_CHOICES,
        default="none",
        help_text="Confidence of the anchor extraction.",
    )
    anchor_edited = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reviewer-edited anchor (overrides anchor_phrase when set).",
    )
    repeated_anchor = models.BooleanField(
        default=False,
        help_text="True if this anchor is already used in another active suggestion for this destination.",
    )
    phrase_match_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-008 phrase-match details for review and debugging.",
    )
    learned_anchor_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-009 learned-anchor diagnostics for review and debugging.",
    )
    rare_term_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-010 rare-term propagation diagnostics for review and debugging.",
    )
    field_aware_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-011 field-aware relevance diagnostics for review and debugging.",
    )
    click_distance_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-012 click-distance context for review and debugging.",
    )
    explore_exploit_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-013 explore/exploit details for review and debugging.",
    )
    cluster_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-014 near-duplicate clustering details for review and debugging.",
    )
    score_slate_diversity = models.FloatField(
        null=True,
        blank=True,
        help_text="FR-015 MMR diversity score for this suggestion's slot in the host slate. Null when diversity reranking is disabled.",
    )
    slate_diversity_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explainable FR-015 MMR slot selection details for review and debugging.",
    )

    # Review state
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
        help_text="Current review/lifecycle status of this suggestion.",
    )
    rejection_reason = models.CharField(
        max_length=100,
        choices=REJECTION_REASON_CHOICES,
        blank=True,
        help_text="Why this suggestion was rejected.",
    )
    reviewer_notes = models.TextField(
        blank=True,
        help_text="Free-text notes from the reviewer.",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a reviewer approved or rejected this suggestion.",
    )

    # Applied / verified tracking
    is_applied = models.BooleanField(
        default=False,
        help_text="True when the reviewer has manually applied this link on the live forum.",
    )
    applied_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the suggestion was marked as applied.",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the link was automatically verified as live via XenForo API.",
    )
    stale_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Why this suggestion became stale (e.g. 'host post edited').",
    )

    # Supersede chain
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
        help_text="Points to the newer suggestion that replaced this one.",
    )
    superseded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this suggestion was superseded.",
    )

    class Meta:
        verbose_name = "Suggestion"
        verbose_name_plural = "Suggestions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-score_final"]),
            models.Index(fields=["destination", "status"]),
            models.Index(fields=["host", "status"]),
            models.Index(fields=["is_applied"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.status}] {self.destination_title[:50]} ← "
            f"'{self.anchor_phrase[:30]}' (score={self.score_final:.3f})"
        )


class PipelineDiagnostic(models.Model):
    """
    Records why a destination was skipped during a pipeline run.
    Powers the 'Why no suggestion?' explorer in the Angular frontend.
    """

    SKIP_REASON_CHOICES = [
        ("already_has_pending", "Already has a pending suggestion"),
        ("no_semantic_matches", "No semantic matches found"),
        ("all_candidates_filtered", "All candidates filtered out"),
        ("no_host_sentences", "No eligible host sentences found"),
        ("score_too_low", "Best match score below threshold"),
        ("no_embedding", "Destination has no embedding"),
        ("max_links_reached", "Host already has max links"),
        ("anchor_banned", "All candidate anchors are banned"),
        ("short_post", "Post too short to distill"),
        ("host_reuse_cap", "Host reuse cap reached"),
        ("circular_suppressed", "Circular candidate suppressed"),
        ("cross_silo_blocked", "Cross-silo candidate blocked by strict mode"),
        ("other", "Other"),
    ]

    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name="diagnostics",
        help_text="The pipeline run this diagnostic belongs to.",
    )
    destination = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="pipeline_diagnostics",
        help_text="The destination content item that was skipped.",
    )
    skip_reason = models.CharField(
        max_length=100,
        choices=SKIP_REASON_CHOICES,
        db_index=True,
        help_text="Short code describing why no suggestion was created.",
    )
    detail = models.JSONField(
        default=dict,
        help_text="Extra diagnostic data (e.g. best score found, threshold used).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this diagnostic record was created.",
    )

    class Meta:
        verbose_name = "Pipeline Diagnostic"
        verbose_name_plural = "Pipeline Diagnostics"
        indexes = [
            models.Index(
                fields=["pipeline_run", "skip_reason"],
                name="suggestions_pipelin_a2cf09_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.skip_reason}] {self.destination} "
            f"in run {str(self.pipeline_run_id)[:8]}"
        )
