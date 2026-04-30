"""
Feature flag evaluation service.
Deterministic rollout via stable hashing (sticky bucketing).
"""

from __future__ import annotations
import hashlib
import logging
from typing import Optional, Any
from django.db import models
from apps.audit.models import FeatureFlag, FeatureFlagExposure

logger = logging.getLogger(__name__)

def is_flag_enabled(
    flag_key: str, 
    user_id: Optional[int] = None,
    log_exposure: bool = False
) -> bool:
    """
    Checks if a feature flag is enabled for the given user.
    
    Args:
        flag_key: Stable key of the flag (e.g. 'ranking:bge-m3-rerank')
        user_id: ID of the user (used for sticky bucketing)
        log_exposure: If True, records a FeatureFlagExposure on access
    """
    try:
        from apps.core.feature_flags import seed_declared_feature_flags

        seed_declared_feature_flags()
    except Exception:  # noqa: BLE001
        logger.debug("[feature_flags] declared flag seed skipped", exc_info=True)

    flag = FeatureFlag.objects.filter(key=flag_key).first()
    if not flag:
        return False
    
    # Simple global on/off
    if not flag.enabled:
        return False
    
    # 100% rollout is always ON
    if flag.rollout_percent >= 100:
        if log_exposure and user_id:
            _record_exposure(flag_key, user_id, "")
        return True
    
    # Partial rollout requires a user_id
    if user_id is None:
        return False
        
    # Sticky bucketing: (user_id + salt) hash % 100
    bucket = _get_bucket(user_id, flag_key)
    is_active = bucket < flag.rollout_percent
    
    if is_active and log_exposure:
        variant = get_flag_variant(flag_key, user_id)
        _record_exposure(flag_key, user_id, variant or "")
        
    return is_active

def get_flag_variant(flag_key: str, user_id: int) -> Optional[str]:
    """
    Resolves the specific A/B variant for a user.
    """
    flag = FeatureFlag.objects.filter(key=flag_key).first()
    if not flag or not flag.variants:
        return None
        
    total_weight = sum(v.get("weight", 0) for v in flag.variants)
    if total_weight <= 0:
        return None
        
    bucket = _get_bucket(user_id, f"{flag_key}:variant")
    
    # Scale bucket (0-99) to total_weight
    scaled_bucket = (bucket / 100.0) * total_weight
    
    current = 0
    for variant in flag.variants:
        current += variant.get("weight", 0)
        if scaled_bucket < current:
            return variant.get("name")
            
    return flag.variants[-1].get("name")

def _get_bucket(user_id: int, salt: str) -> int:
    """Deterministic 0-99 bucket."""
    raw = f"{user_id}:{salt}".encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    # Take first 8 chars, convert to int, mod 100
    return int(h[:8], 16) % 100

def _record_exposure(flag_key: str, user_id: int, variant: str):
    """Async exposure logging (best effort)."""
    try:
        FeatureFlagExposure.objects.create(
            key=flag_key,
            user_id=user_id,
            variant=variant
        )
    except Exception:
        logger.error("[feature_flags] Failed to record exposure", exc_info=True)

def serialise_flags_for_user(user_id: Optional[int]) -> list[dict[str, Any]]:
    """Snapshot of all active flags for the frontend."""
    try:
        from apps.core.feature_flags import seed_declared_feature_flags

        seed_declared_feature_flags()
    except Exception:  # noqa: BLE001
        logger.debug("[feature_flags] declared flag seed skipped", exc_info=True)

    out = []
    # Only return flags that are at least partially enabled
    for flag in FeatureFlag.objects.filter(enabled=True):
        if is_flag_enabled(flag.key, user_id, log_exposure=False):
            entry = {"key": flag.key, "enabled": True}
            if user_id:
                variant = get_flag_variant(flag.key, user_id)
                if variant:
                    entry["variant"] = variant
            out.append(entry)
    return out
