"""Shared profiling-proof marker rules for hooks and Docker commands."""

from __future__ import annotations

PROFILE_GAP_CATEGORIES = (
    "collector",
    "backend",
    "versions",
    "permissions",
    "sampling",
    "retention",
    "dashboards",
    "trace-profile-correlation",
)
PROFILE_GAP_CATEGORY_TEXT = ",".join(PROFILE_GAP_CATEGORIES)
PROFILE_PROOF_DECISIONS = frozenset(
    {"optimized", "not-relevant", "not-achievable", "autoissue-filed"}
)
NATIVE_REWRITE_LABEL = "performance-native-rewrite"
NATIVE_REWRITE_REQUIRED_FIELDS = frozenset(
    {
        "hotspot",
        "before",
        "after",
        "current_ceiling",
        "reason",
        "expected_speedup",
        "target_language",
        "cost",
        "integration",
        "tests",
        "reuse_check",
        "canonical",
        "default_path",
        "python_fallback",
        "risks",
        "rollback",
        "autoissue",
        "label",
    }
)
