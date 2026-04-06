import logging
from django.conf import settings
from apps.pipeline.tasks import sync_single_xf_item, sync_single_wp_item
from apps.sync.models import WebhookReceipt

logger = logging.getLogger(__name__)

def record_webhook(source, event_type, payload, status='received', error_message='', sync_job=None):
    """Log a webhook receipt to the database for the audit log."""
    try:
        return WebhookReceipt.objects.create(
            source=source,
            event_type=event_type,
            payload=payload,
            status=status,
            error_message=error_message,
            sync_job=sync_job
        )
    except Exception as e:
        logger.error("Failed to record webhook receipt: %s", e)
        return None

def _get_webhook_secret(app_setting_key: str, env_var: str) -> str:
    """Check AppSetting first, fall back to Django env var."""
    try:
        from apps.core.models import AppSetting
        db = AppSetting.objects.filter(key=app_setting_key).first()
        if db and db.value:
            return db.value
    except Exception:
        pass
    return getattr(settings, env_var, "")

def verify_xf_signature(payload_body, signature):
    """
    Verify that the webhook comes from XenForo.
    XF sends X-Xf-Webhook-Secret in the header if configured.
    """
    secret = _get_webhook_secret("webhook.xenforo_secret", "XENFORO_WEBHOOK_SECRET")
    if not secret:
        logger.warning("XENFORO_WEBHOOK_SECRET is not set.")
        return True

    return payload_body == secret or signature == secret

def verify_wp_signature(payload_body, signature):
    """
    Verify that the webhook comes from WordPress.
    We expect the same secret mechanism as XF for simplicity.
    """
    secret = _get_webhook_secret("webhook.wordpress_secret", "WORDPRESS_WEBHOOK_SECRET")
    if not secret:
        logger.warning("WORDPRESS_WEBHOOK_SECRET is not set.")
        return True

    return payload_body == secret or signature == secret

def process_xf_webhook(event_type, payload):
    """
    Parse the XenForo webhook payload and trigger internal sync tasks.
    """
    logger.info("Processing XF Webhook: event=%s, type=%s, id=%s", 
                event_type, payload.get("content_type"), payload.get("content_id"))

    sync_job_id = None
    status = 'processed'
    error_message = ''

    try:
        if event_type in ["thread_insert", "thread_update"]:
            thread_id = payload.get("content_id")
            node_id = payload.get("node_id")
            if thread_id:
                res = sync_single_xf_item.delay(thread_id, content_type="thread", node_id=node_id)
                sync_job_id = res.id
            else:
                status = 'ignored'
                error_message = 'Missing thread_id'

        elif event_type in ["post_insert", "post_update"]:
            thread_id = payload.get("data", {}).get("thread_id") or payload.get("thread_id")
            if thread_id:
                res = sync_single_xf_item.delay(thread_id, content_type="thread")
                sync_job_id = res.id
            else:
                status = 'ignored'
                error_message = 'Missing thread_id'

        elif event_type == "thread_delete":
            from apps.content.models import ContentItem
            thread_id = payload.get("content_id")
            if thread_id:
                ContentItem.objects.filter(content_id=thread_id, content_type="thread").update(is_deleted=True)
                logger.info("Marked thread %s as deleted via webhook.", thread_id)
            else:
                status = 'ignored'
                error_message = 'Missing thread_id'
        else:
            status = 'ignored'
            error_message = f'Event type {event_type} not handled'
            
    except Exception as e:
        status = 'error'
        error_message = str(e)
        logger.exception("Error processing XF webhook")

    # Record the receipt
    record_webhook(
        source='api', 
        event_type=event_type, 
        payload=payload, 
        status=status, 
        error_message=error_message
        # Note: sync_job link might need the actual SyncJob model instance, 
        # but tasks are async, so we might skip linking for now or link by ID if we add it.
    )
    return status == 'processed'

def process_wp_webhook(event_type, payload):
    """
    Parse the WordPress webhook payload and trigger internal sync tasks.
    
    Expected payload:
    {
        "event": "post_updated",
        "post_id": 123,
        "post_type": "post" | "page"
    }
    """
    logger.info("Processing WP Webhook: event=%s, id=%s", event_type, payload.get("post_id"))
    
    status = 'processed'
    error_message = ''
    
    try:
        post_id = payload.get("post_id")
        post_type = payload.get("post_type", "post")
        
        if post_id:
            sync_single_wp_item.delay(post_id, content_type=post_type)
        else:
            status = 'ignored'
            error_message = 'Missing post_id'
            
    except Exception as e:
        status = 'error'
        error_message = str(e)
        logger.exception("Error processing WP webhook")
        
    record_webhook(
        source='wp',
        event_type=event_type or 'wp_update',
        payload=payload,
        status=status,
        error_message=error_message
    )
    return status == 'processed'
