"""
Unified audit logging service.
Provides a central record_audit helper used across the application.
"""

import logging
from typing import Any, Optional, Union
from django.db import models
from django.http import HttpRequest
from apps.audit.models import AuditEntry

logger = logging.getLogger(__name__)

def record_audit(
    action: str,
    target: Union[models.Model, str, tuple[str, str]],
    detail: Optional[dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
    ip_address: Optional[str] = None,
) -> AuditEntry:
    """
    Records a significant action in the Audit Trail.
    
    Args:
        action: The action code (must be in AuditEntry.ACTION_CHOICES)
        target: The object being acted upon. Can be:
                - A Django model instance
                - A string (target_type)
                - A tuple of (target_type, target_id)
        detail: Optional dictionary of extra context
        request: Optional HttpRequest to extract IP address
        ip_address: Explicitly provided IP address
    """
    # 1. Resolve target_type and target_id
    if isinstance(target, models.Model):
        target_type = target._meta.model_name
        target_id = str(target.pk)
    elif isinstance(target, tuple):
        target_type, target_id = target
    else:
        target_type = str(target)
        target_id = "0" # Generic target

    # 2. Resolve IP address
    if not ip_address and request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')

    # 3. Create the entry
    entry = AuditEntry.objects.create(
        action=action,
        target_type=target_type[:50],
        target_id=target_id[:100],
        detail=detail or {},
        ip_address=ip_address,
    )
    
    logger.debug(f"[audit] Recorded: {entry}")
    return entry

# Alias for Slice 5 "AuditEvent" nomenclature
record_event = record_audit
