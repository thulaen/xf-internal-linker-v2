"""
Graph models — existing links between content items.

ExistingLink tracks links that are already live on the forum.
This data feeds the D3.js link graph visualization and is used by the
pipeline to avoid suggesting links that already exist.
"""

import uuid

from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimestampedModel


class ExistingLink(models.Model):
    """
    A link that already exists from one content item to another on the live forum.

    Populated during sync by parsing BBCode in post bodies.
    The pipeline checks this table to avoid suggesting duplicate links.
    Used by the D3.js link graph to show the current link topology.
    """

    EXTRACTION_METHOD_CHOICES = [
        ("bbcode_anchor", "BBCode Anchor"),
        ("html_anchor", "HTML Anchor"),
        ("bare_url", "Bare URL"),
    ]

    CONTEXT_CLASS_CHOICES = [
        ("contextual", "Contextual"),
        ("weak_context", "Weak Context"),
        ("isolated", "Isolated"),
    ]

    from_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="outgoing_links",
        help_text="The content item that contains this link (the host).",
    )
    to_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="incoming_links",
        help_text="The content item being linked to (the destination).",
    )
    anchor_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="The anchor text used for this link on the live forum.",
    )
    extraction_method = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=EXTRACTION_METHOD_CHOICES,
        help_text="How this link was extracted from the source body.",
    )
    link_ordinal = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Zero-based order of this internal link within the source body.",
    )
    source_internal_link_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total resolved internal links on the source item after destination deduplication.",
    )
    context_class = models.CharField(
        max_length=30,
        blank=True,
        default="",
        choices=CONTEXT_CLASS_CHOICES,
        help_text="Whether the link appears in contextual prose, weak context, or isolated markup.",
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this link was first detected during a sync.",
    )

    class Meta:
        verbose_name = "Existing Link"
        verbose_name_plural = "Existing Links"
        unique_together = [["from_content_item", "to_content_item", "anchor_text"]]
        indexes = [
            models.Index(fields=["to_content_item"]),
            models.Index(fields=["from_content_item"]),
            models.Index(fields=["from_content_item", "link_ordinal"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_content_item} → {self.to_content_item} ('{self.anchor_text[:40]}')"


class LinkFreshnessEdge(models.Model):
    """History row for one unique source-to-destination internal-link relationship."""

    from_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="freshness_outgoing_links",
        help_text="The source content item that linked to the destination.",
    )
    to_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="freshness_incoming_links",
        help_text="The destination content item that received the inbound link.",
    )
    first_seen_at = models.DateTimeField(
        help_text="When this source-to-destination link was first seen during a safe body parse.",
    )
    last_seen_at = models.DateTimeField(
        help_text="When this source-to-destination link was last confirmed during a safe body parse.",
    )
    last_disappeared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this link was last confirmed missing during a safe body parse.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="True when this source-to-destination link is currently active.",
    )

    class Meta:
        verbose_name = "Link Freshness Edge"
        verbose_name_plural = "Link Freshness Edges"
        constraints = [
            models.UniqueConstraint(
                fields=["from_content_item", "to_content_item"],
                name="graph_unique_link_freshness_edge",
            )
        ]
        indexes = [
            models.Index(fields=["to_content_item", "is_active"]),
            models.Index(fields=["to_content_item", "first_seen_at"]),
            models.Index(fields=["to_content_item", "last_disappeared_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_content_item} -> {self.to_content_item} [active={self.is_active}]"


class DirectionalTransitionEdge(models.Model):
    """Compact ordered visitor movement counts for DSTP ranking input."""

    SOURCE_MATOMO = "matomo"
    SOURCE_GA4 = "ga4"
    SOURCE_COMBINED = "combined"
    SOURCE_CHOICES = [
        (SOURCE_MATOMO, "Matomo"),
        (SOURCE_GA4, "Google Analytics 4"),
        (SOURCE_COMBINED, "Deduped Matomo and Google Analytics 4"),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    site_id = models.CharField(max_length=32, blank=True, db_index=True)
    source_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="dstp_outgoing_transitions",
    )
    dest_content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="dstp_incoming_transitions",
    )
    transition_count = models.PositiveIntegerField(default=0)
    source_transition_count = models.PositiveIntegerField(default=0)
    data_window_start = models.DateField()
    data_window_end = models.DateField()
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Directional Transition Edge"
        verbose_name_plural = "Directional Transition Edges"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source",
                    "site_id",
                    "source_content_item",
                    "dest_content_item",
                ],
                name="graph_unique_directional_transition_edge",
            )
        ]
        indexes = [
            models.Index(fields=["source_content_item", "source"]),
            models.Index(fields=["dest_content_item", "source"]),
            models.Index(fields=["source", "data_window_end"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source}:{self.site_id} "
            f"{self.source_content_item_id} -> {self.dest_content_item_id} "
            f"({self.transition_count})"
        )


class BrokenLink(TimestampedModel):
    """A URL detected in a content item that needs link-health review."""

    STATUS_OPEN = "open"
    STATUS_IGNORED = "ignored"
    STATUS_FIXED = "fixed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IGNORED, "Ignored"),
        (STATUS_FIXED, "Fixed"),
    ]

    broken_link_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Stable UUID used by the API and Angular frontend.",
    )
    source_content = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="broken_links",
        help_text="The content item where this URL was found.",
    )
    url = models.URLField(
        max_length=2048,
        help_text="The URL found in the source content.",
    )
    http_status = models.IntegerField(
        default=0,
        help_text="Last HTTP status code seen for this URL. 0 means connection error or timeout.",
    )
    redirect_url = models.URLField(
        max_length=2048,
        blank=True,
        default="",
        help_text="Redirect destination when the URL responds with a redirect status.",
    )
    first_detected_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this issue was first detected by the scanner.",
    )
    last_checked_at = models.DateTimeField(
        auto_now=True,
        help_text="When the scanner last checked this URL.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
        help_text="Manual review state for this broken-link record.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Reviewer notes about why the record was ignored or fixed.",
    )

    class Meta:
        verbose_name = "Broken Link"
        verbose_name_plural = "Broken Links"
        ordering = ["status", "-last_checked_at", "-first_detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_content", "url"],
                name="graph_unique_broken_link_source_url",
            )
        ]
        indexes = [
            models.Index(fields=["status", "http_status"]),
            models.Index(fields=["source_content", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_content} -> {self.url} [{self.http_status}]"


class GraphSignalRun(TimestampedModel):
    """
    A single snapshot of computed graph signals for the entire site.
    Uses skip-if-unchanged (by graph_hash) to avoid redundant computation.
    """

    STATUS_COMPUTING = "computing"
    STATUS_CURRENT = "current"
    STATUS_SUPERSEDED = "superseded"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_COMPUTING, "Computing"),
        (STATUS_CURRENT, "Current"),
        (STATUS_SUPERSEDED, "Superseded"),
        (STATUS_FAILED, "Failed"),
    ]

    graph_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of the sorted active edges used to build the graph.",
    )
    signal_version = models.CharField(
        max_length=50,
        help_text="Version identifier of the signal-computation logic.",
    )
    node_count = models.IntegerField(
        help_text="Number of nodes (content items) in this graph.",
    )
    edge_count = models.IntegerField(
        help_text="Number of edges (links) in this graph.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_COMPUTING,
        db_index=True,
        help_text="Lifecycle state of this run.",
    )
    computed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this run finished computing and became current.",
    )
    params_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Configuration and hyperparameter snapshot used for this run.",
    )
    sbma_matrix_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="SBMA block-to-block link probability matrix for this run.",
    )

    class Meta:
        verbose_name = "Graph Signal Run"
        verbose_name_plural = "Graph Signal Runs"
        indexes = [
            models.Index(fields=["graph_hash", "signal_version", "status"]),
        ]

    def __str__(self) -> str:
        prefix = self.graph_hash[:32] if self.graph_hash else "None"
        return f"Run {prefix}... ({self.signal_version})"


class NodeGraphSignal(models.Model):
    """
    Per-node (content item) structural signals computed during a specific run.
    """

    run = models.ForeignKey(
        GraphSignalRun,
        on_delete=models.CASCADE,
        related_name="node_signals",
        help_text="The snapshot run that produced this signal.",
    )
    content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="graph_signals",
        help_text="The content item these signals describe.",
    )

    # Signals 2 & 3: Communities & Betweenness
    community_id = models.IntegerField(
        null=True, blank=True, help_text="Louvain community partition ID."
    )
    icpc_local_indegree = models.PositiveIntegerField(
        default=0,
        help_text="Incoming links from the same large-enough Louvain community.",
    )
    icpc_global_indegree = models.PositiveIntegerField(
        default=0,
        help_text="All incoming links to this content item in the graph snapshot.",
    )
    tosd_lambda = models.FloatField(
        null=True,
        blank=True,
        help_text="TOSD normalized-Laplacian variation value for this content item.",
    )
    sbma_block_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="SBMA structural block assigned to this content item.",
    )
    betweenness = models.FloatField(
        null=True, blank=True, help_text="Betweenness centrality score."
    )

    # Signals 4 & 5: Reach & Centrality Panel
    click_depth = models.IntegerField(
        null=True, blank=True, help_text="Shortest path distance from hub seeds."
    )
    inbound_reachable = models.BooleanField(
        default=True, help_text="Whether this node can be reached from hubs."
    )
    is_orphan = models.BooleanField(
        default=False, help_text="True if in-degree is 0."
    )
    eigenvector = models.FloatField(
        null=True, blank=True, help_text="Eigenvector centrality score."
    )
    katz = models.FloatField(
        null=True, blank=True, help_text="Katz centrality score."
    )
    closeness = models.FloatField(
        null=True, blank=True, help_text="Closeness centrality score."
    )

    # Signals 6,7,8,10
    core_number = models.IntegerField(
        null=True, blank=True, help_text="k-core decomposition shell number."
    )
    component_id = models.IntegerField(
        null=True, blank=True, help_text="Weakly connected component ID."
    )
    is_main_component = models.BooleanField(
        default=False, help_text="True if part of the largest connected component."
    )
    local_clustering = models.FloatField(
        null=True, blank=True, help_text="Local clustering coefficient."
    )
    group_seed_rank = models.IntegerField(
        null=True, blank=True, help_text="Rank order as a group-closeness seed."
    )

    # Signal 9: node2vec embedding
    node2vec_embedding = VectorField(
        dimensions=768,  # Or whatever dim the existing node2vec uses.
        null=True,
        blank=True,
        help_text="Structural embedding vector from node2vec.",
    )

    class Meta:
        verbose_name = "Node Graph Signal"
        verbose_name_plural = "Node Graph Signals"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "content_item"],
                name="graph_unique_node_signal_per_run",
            )
        ]

    def __str__(self) -> str:
        return f"Node Signal for {self.content_item} (Run {self.run_id})"


class LinkPredictionCandidate(models.Model):
    """
    Candidate links proposed by structural link prediction algorithms.
    Capped to top-K per source per run.
    """

    run = models.ForeignKey(
        GraphSignalRun,
        on_delete=models.CASCADE,
        related_name="link_candidates",
        help_text="The snapshot run that produced this candidate.",
    )
    from_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="link_predictions_out",
        help_text="Proposed source content item.",
    )
    to_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="link_predictions_in",
        help_text="Proposed destination content item.",
    )

    # Signal 1: Link Prediction
    adamic_adar = models.FloatField(
        null=True, blank=True, help_text="Adamic-Adar index score."
    )
    common_neighbors = models.FloatField(
        null=True, blank=True, help_text="Common neighbors count."
    )
    jaccard = models.FloatField(
        null=True, blank=True, help_text="Jaccard similarity of neighborhoods."
    )

    # Flag signals from communities/betweenness
    same_community = models.BooleanField(
        default=False, help_text="True if both nodes are in the same Louvain community."
    )
    is_bridge = models.BooleanField(
        default=False, help_text="True if this candidate connects different communities."
    )

    # Structural embedding cosine
    embed_cosine = models.FloatField(
        null=True, blank=True, help_text="Cosine similarity of their node2vec embeddings."
    )

    class Meta:
        verbose_name = "Link Prediction Candidate"
        verbose_name_plural = "Link Prediction Candidates"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "from_item", "to_item"],
                name="graph_unique_link_prediction_candidate_per_run",
            )
        ]

    def __str__(self) -> str:
        return f"Candidate {self.from_item} -> {self.to_item}"
