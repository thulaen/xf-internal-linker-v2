import hmac
import logging

from django.conf import settings
from django.core.cache import cache
from apps.pipeline.tasks import sync_single_xf_item, sync_single_wp_item
from apps.sync.models import WebhookReceipt

# Lock TTL for webhook idempotency — prevents duplicate task execution
# when a webhook arrives while a previous task for the same item is running.
_WEBHOOK_LOCK_TTL = 300  # 5 minutes

logger = logging.getLogger(__name__)

# How long to cache webhook secrets (seconds).  Secrets rarely change, so 60s
# is a safe TTL that avoids a DB hit on every incoming webhook request.
_SECRET_CACHE_TTL = 60


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
    except Exception:
        logger.exception("Failed to record webhook receipt for %s/%s", source, event_type)
        raise


def _get_webhook_secret(app_setting_key: str, env_var: str) -> str:
    """Return the webhook secret, checking AppSetting first then the env var.

    The result is cached for _SECRET_CACHE_TTL seconds so that burst webhook
    traffic does not hammer the database with repeated lookups.
    """
    cache_key = f"webhook_secret:{app_setting_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    secret = ""
    try:
        from apps.core.models import AppSetting
        db = AppSetting.objects.filter(key=app_setting_key).first()
        if db and db.value:
            secret = db.value
    except Exception:
        logger.debug("Could not load webhook secret from AppSetting %s", app_setting_key, exc_info=True)

    if not secret:
        secret = getattr(settings, env_var, "")

    # Cache even an empty string to avoid repeated DB misses; the TTL is short.
    cache.set(cache_key, secret, _SECRET_CACHE_TTL)
    return secret


def verify_xf_signature(signature):
    """
    Verify that the webhook comes from XenForo.

    XenForo sends the shared secret verbatim in the X-XF-Webhook-Secret header
    (not an HMAC digest — this is XenForo's own webhook authentication scheme).
    Constant-time comparison prevents timing-based secret enumeration attacks.
    Rejects the request when no secret is configured (fail-closed).
    """
    secret = _get_webhook_secret("webhook.xenforo_secret", "XENFORO_WEBHOOK_SECRET")
    if not secret:
        logger.error("XENFORO_WEBHOOK_SECRET is not set — rejecting webhook.")
        return False

    if not signature:
        return False

    return hmac.compare_digest(signature, secret)


def verify_wp_signature(signature):
    """
    Verify that the webhook comes from WordPress.

    The WP webhook plugin sends the shared secret verbatim in the
    X-Wp-Webhook-Secret header (or as a body field).
    Constant-time comparison prevents timing-based secret enumeration attacks.
    Rejects the request when no secret is configured (fail-closed).
    """
    secret = _get_webhook_secret("webhook.wordpress_secret", "WORDPRESS_WEBHOOK_SECRET")
    if not secret:
        logger.error("WORDPRESS_WEBHOOK_SECRET is not set — rejecting webhook.")
        return False

    if not signature:
        return False

    return hmac.compare_digest(signature, secret)

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
                lock_key = f"webhook_lock:xf_thread:{thread_id}"
                if cache.add(lock_key, "1", _WEBHOOK_LOCK_TTL):
                    task_id = f"xf_sync_thread_{thread_id}"
                    res = sync_single_xf_item.apply_async(
                        args=[thread_id],
                        kwargs={"content_type": "thread", "node_id": node_id},
                        task_id=task_id,
                    )
                    sync_job_id = res.id
                else:
                    status = 'ignored'
                    error_message = 'Duplicate webhook — task already in progress'
                    logger.info("Skipping duplicate webhook for XF thread %s", thread_id)
            else:
                status = 'ignored'
                error_message = 'Missing thread_id'

        elif event_type in ["post_insert", "post_update"]:
            thread_id = payload.get("data", {}).get("thread_id") or payload.get("thread_id")
            if thread_id:
                lock_key = f"webhook_lock:xf_thread:{thread_id}"
                if cache.add(lock_key, "1", _WEBHOOK_LOCK_TTL):
                    task_id = f"xf_sync_thread_{thread_id}"
                    res = sync_single_xf_item.apply_async(
                        args=[thread_id],
                        kwargs={"content_type": "thread"},
                        task_id=task_id,
                    )
                    sync_job_id = res.id
                else:
                    status = 'ignored'
                    error_message = 'Duplicate webhook — task already in progress'
                    logger.info("Skipping duplicate webhook for XF thread %s (post event)", thread_id)
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
            lock_key = f"webhook_lock:wp_{post_type}:{post_id}"
            if cache.add(lock_key, "1", _WEBHOOK_LOCK_TTL):
                task_id = f"wp_sync_{post_type}_{post_id}"
                sync_single_wp_item.apply_async(
                    args=[post_id],
                    kwargs={"content_type": post_type},
                    task_id=task_id,
                )
            else:
                status = 'ignored'
                error_message = 'Duplicate webhook — task already in progress'
                logger.info("Skipping duplicate webhook for WP %s %s", post_type, post_id)
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
