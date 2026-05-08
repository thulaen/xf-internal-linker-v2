"""Declared feature flags seeded into the database."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeclaredFeatureFlag:
    key: str
    description: str
    default_enabled: bool = True
    rollout_percent: int = 100
    variants: tuple[dict[str, int | str], ...] = field(default_factory=tuple)


DECLARED_FEATURE_FLAGS: tuple[DeclaredFeatureFlag, ...] = (
    DeclaredFeatureFlag(
        key="operations-feed",
        description="Show the live Operations Feed narration surface.",
    ),
    DeclaredFeatureFlag(
        key="suggestion-readiness-gate",
        description="Block Review until prerequisite data is ready.",
    ),
    DeclaredFeatureFlag(
        key="meta-algorithms-expanded-registry",
        description="Show active and spec-only meta algorithms in Settings.",
    ),
)


def seed_declared_feature_flags() -> int:
    """Create missing declared flags without overwriting operator choices."""
    from apps.audit.models import FeatureFlag

    created = 0
    for flag in DECLARED_FEATURE_FLAGS:
        _, was_created = FeatureFlag.objects.get_or_create(
            key=flag.key,
            defaults={
                "description": flag.description,
                "enabled": flag.default_enabled,
                "rollout_percent": flag.rollout_percent,
                "variants": list(flag.variants),
            },
        )
        if was_created:
            created += 1
    return created


__all__ = [
    "DECLARED_FEATURE_FLAGS",
    "DeclaredFeatureFlag",
    "seed_declared_feature_flags",
]
