"""
Per-endpoint rate throttles for expensive operations.

Applied on top of the global DRF defaults (anon: 100/hour, user: 1000/hour).
Each throttle scope uses its own counter, so a user hitting graph_rebuild
does not consume their general 1000/hour allowance.
"""

from rest_framework.throttling import UserRateThrottle


class GraphRebuildThrottle(UserRateThrottle):
    """Graph rebuild triggers PageRank recomputation — limit to 6/hour."""

    scope = "graph_rebuild"
    rate = "6/hour"


class WeightRecalcThrottle(UserRateThrottle):
    """Authority, freshness, click-distance, clustering recalculations."""

    scope = "weight_recalc"
    rate = "12/hour"


class CoOccurrenceComputeThrottle(UserRateThrottle):
    """Full session-matrix computation — heavy CPU work."""

    scope = "cooccurrence_compute"
    rate = "6/hour"


class ImportTriggerThrottle(UserRateThrottle):
    """Prevent import queue flooding."""

    scope = "import_trigger"
    rate = "2/minute"


class MLEmbedThrottle(UserRateThrottle):
    """GPU/CPU-bound embedding and distillation batch processing."""

    scope = "ml_embed"
    rate = "5/minute"


class ChallengerEvalThrottle(UserRateThrottle):
    """Weight challenger evaluation — expensive optimization math."""

    scope = "challenger_eval"
    rate = "1/minute"


class SettingsWriteThrottle(UserRateThrottle):
    """Settings PUT endpoints — prevent config thrashing."""

    scope = "settings_write"
    rate = "10/minute"


class CompressionAuditRunThrottle(UserRateThrottle):
    """Phase 4.9 — synchronous compression audit. Each run takes 30-120 s
    and walks ~10k rows of zlib compression; rate-limit so an
    accidentally-mashed button (or compromised token) can't pin the
    request worker.
    """

    scope = "compression_audit_run"
    rate = "3/hour"
