"""
Sync app views — content import endpoints.
"""

import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from .models import SyncJob, WebhookReceipt
from .serializers import SyncJobSerializer, WebhookReceiptSerializer


ALLOWED_MODES = {"full", "titles", "quick"}
MAX_UPLOAD_MB = 200


class ImportUploadView(APIView):
    """Accept a JSONL export file from the user's browser and start an import job.
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file provided."}, status=400)

        if not file_obj.name.lower().endswith(".jsonl"):
            return Response({"error": "Only .jsonl files are accepted."}, status=400)

        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
        if file_obj.size > max_bytes:
            return Response(
                {"error": f"File exceeds the {MAX_UPLOAD_MB} MB limit."}, status=400
            )

        mode = request.data.get("mode", "full")
        if mode not in ALLOWED_MODES:
            return Response({"error": f"Invalid mode '{mode}'."}, status=400)

        # Save to BASE_DIR/data/imports/ 
        imports_dir = Path(settings.BASE_DIR) / "data" / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4().hex}.jsonl"
        dest_path = imports_dir / safe_name
        with open(dest_path, "wb") as fh:
            for chunk in file_obj.chunks():
                fh.write(chunk)

        job = SyncJob.objects.create(
            source="jsonl",
            mode=mode,
            file_name=file_obj.name,
            status="pending"
        )
        job_id = str(job.job_id)

        from apps.pipeline.tasks import dispatch_import_content

        dispatch_import_content(
            mode=mode,
            source="jsonl",
            file_path=str(dest_path),
            job_id=job_id,
        )

        return Response({
            "job_id": job_id,
            "file": file_obj.name,
            "mode": mode,
        }, status=202)


class SyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing synchronization jobs (imports).
    """
    queryset = SyncJob.objects.all()
    serializer_class = SyncJobSerializer
    lookup_field = "job_id"

    @action(detail=False, methods=["get"])
    def source_status(self, request):
        """
        GET /api/sync-jobs/source_status/
        """
        from apps.core.views import _get_app_setting_value

        xf_url = (_get_app_setting_value("xenforo.base_url") or "").strip()
        xf_key = (_get_app_setting_value("xenforo.api_key") or "").strip()

        wp_url = (_get_app_setting_value("wordpress.base_url") or "").strip()
        wp_user = (_get_app_setting_value("wordpress.username") or "").strip()
        wp_pass = (_get_app_setting_value("wordpress.app_password") or "").strip()

        return Response({
            "api": bool(xf_url and xf_key),
            "wp": bool(wp_url and wp_user and wp_pass),
        })

    @action(detail=False, methods=["post"])
    def trigger_api_sync(self, request):
        """
        Trigger a direct API sync for a specific source (api|wp).
        """
        source = request.data.get("source")
        mode = request.data.get("mode", "full")
        scope_ids = request.data.get("scope_ids", [])

        if source not in ["api", "wp"]:
            return Response({"error": "Invalid source. Use 'api' or 'wp'."}, status=400)
            
        if mode not in ALLOWED_MODES:
            return Response({"error": f"Invalid mode '{mode}'."}, status=400)

        job = SyncJob.objects.create(
            source=source,
            mode=mode,
            status="pending"
        )
        job_id = str(job.job_id)

        from apps.pipeline.tasks import dispatch_import_content
        
        dispatch_import_content(
            mode=mode,
            source=source,
            scope_ids=scope_ids,
            job_id=job_id,
        )

        return Response({
            "job_id": job_id,
            "source": source,
            "mode": mode,
        }, status=202)


class WebhookReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing webhook audit logs.
    """
    queryset = WebhookReceipt.objects.all()
    serializer_class = WebhookReceiptSerializer
    lookup_field = "receipt_id"


class XenForoWebhookView(APIView):
    """
    Real-time webhook receiver for XenForo forum events.
    """
    permission_classes = [] 
    authentication_classes = []

    def post(self, request):
        from .services.webhooks import verify_xf_signature, process_xf_webhook
        
        signature = request.headers.get("XF-Webhook-Secret")
        if not verify_xf_signature(request.body.decode('utf-8'), signature):
            return Response({"error": "Invalid webhook secret"}, status=403)

        event_type = request.headers.get("XF-Webhook-Event") or request.data.get("event")
        if not event_type:
            return Response({"error": "Missing event type"}, status=400)

        success = process_xf_webhook(event_type, request.data)
        return Response({"status": "received" if success else "ignored", "event": event_type}, status=200)


class WordPressWebhookView(APIView):
    """
    Real-time webhook receiver for WordPress post updates.
    
    POST /api/v1/sync/webhooks/wordpress/
    """
    permission_classes = [] 
    authentication_classes = []

    def post(self, request):
        from .services.webhooks import verify_wp_signature, process_wp_webhook
        
        # Security: we use X-Wp-Webhook-Secret or simple body field
        signature = request.headers.get("X-Wp-Webhook-Secret") or request.data.get("secret")
        if not verify_wp_signature(request.body.decode('utf-8'), signature):
            return Response({"error": "Invalid webhook secret"}, status=403)

        event_type = request.data.get("event", "wp_update")
        success = process_wp_webhook(event_type, request.data)
        return Response({"status": "received" if success else "ignored", "event": event_type}, status=200)
