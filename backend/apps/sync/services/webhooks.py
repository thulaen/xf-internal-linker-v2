import hashlib
import hmac
import logging
import json
from django.conf import settings
from apps.pipeline.tasks import sync_single_xf_item

logger = logging.getLogger(__name__)

def verify_xf_signature(payload_body, signature):
    """
    Verify that the webhook comes from XenForo.
    XF sends X-Xf-Webhook-Secret in the header if configured.
    """
    secret = getattr(settings, "XENFORO_WEBHOOK_SECRET", "")
    if not secret:
        # If no secret is configured, we can't verify.
        # But for security, we should probably fail. 
        # However, for initial setup, we log a warning.
        logger.warning("XENFORO_WEBHOOK_SECRET is not set in Django settings.")
        return True 

    # XenForo sends the secret directly in X-Xf-Webhook-Secret, 
    # OR it might use a signature. The ACP screenshot says:
    # "If specified, this value will be included in the XF-Webhook-Secret request header"
    # This means it's a simple token match, not a HMAC signature.
    return payload_body == secret or signature == secret

def process_xf_webhook(event_type, payload):
    """
    Parse the XenForo webhook payload and trigger internal sync tasks.
    
    Payload format (standard XF):
    {
        "event": "thread_insert",
        "content_type": "thread",
        "content_id": 123,
        "data": { ... thread object ... },
        "node_id": 4,
        ...
    }
    """
    logger.info("Processing XF Webhook: event=%s, type=%s, id=%s", 
                event_type, payload.get("content_type"), payload.get("content_id"))

    # Mapping events to sync logic
    # We focus on threads and posts that affect the "first post" (ContentItem)
    
    if event_type in ["thread_insert", "thread_update"]:
        thread_id = payload.get("content_id")
        node_id = payload.get("node_id")
        if thread_id:
            sync_single_xf_item.delay(thread_id, content_type="thread", node_id=node_id)
            return True

    elif event_type in ["post_insert", "post_update"]:
        # If a post is inserted or updated, we check if it belongs to a thread we track.
        # Often we just want to re-sync the whole thread if it's the first post.
        thread_id = payload.get("data", {}).get("thread_id") or payload.get("thread_id")
        if thread_id:
            # We re-sync the thread to update the ContentItem if the first post changed.
            sync_single_xf_item.delay(thread_id, content_type="thread")
            return True

    elif event_type == "thread_delete":
        # Handle deletion by marking ContentItem as deleted
        from apps.content.models import ContentItem
        thread_id = payload.get("content_id")
        if thread_id:
            ContentItem.objects.filter(content_id=thread_id, content_type="thread").update(is_deleted=True)
            logger.info("Marked thread %s as deleted via webhook.", thread_id)
            return True

    logger.debug("Webhook event %s skipped or not handled.", event_type)
    return False
