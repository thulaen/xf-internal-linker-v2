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
from .models import SyncJob
from .serializers import SyncJobSerializer


ALLOWED_MODES = {"full", "titles", "quick"}
MAX_UPLOAD_MB = 200


class ImportUploadView(APIView):
    """Accept a JSONL export file from the user's browser and start an import job.

    POST /api/import/upload/
    Content-Type: multipart/form-data

    Form fields:
        file   — the .jsonl export file (required)
        mode   — 'full' | 'titles' | 'quick' (default: 'full')

    Response:
        { "job_id": "<uuid>", "file": "<original name>", "mode": "<mode>" }

    The returned job_id can be used to subscribe to WebSocket progress at
        ws://<host>/ws/jobs/<job_id>/
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

        # Save to BASE_DIR/data/imports/ — stays within project root for security check
        imports_dir = Path(settings.BASE_DIR) / "data" / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4().hex}.jsonl"
        dest_path = imports_dir / safe_name
        with open(dest_path, "wb") as fh:
            for chunk in file_obj.chunks():
                fh.write(chunk)

        # Create SyncJob record to track progress and history
        from apps.sync.models import SyncJob
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


class XenForoWebhookView(APIView):
    """
    Real-time webhook receiver for XenForo forum events.
    
    POST /api/v1/sync/webhooks/xenforo/
    Headers:
        XF-Webhook-Secret: <your-configured-secret>
        XF-Webhook-Event: thread_insert | post_update | etc.
    """
    permission_classes = [] # Public endpoint, handled by internal signature check
    authentication_classes = []

    def post(self, request):
        from .services.webhooks import verify_xf_signature, process_xf_webhook
        
        # 1. Security Check
        # XF puts the secret in the 'XF-Webhook-Secret' header
        signature = request.headers.get("XF-Webhook-Secret")
        # In some XF versions, it might be in the POST body or another header.
        # We also support checking against the raw body if it's a signature.
        if not verify_xf_signature(request.body.decode('utf-8'), signature):
            return Response({"error": "Invalid webhook secret"}, status=403)

        # 2. Extract Event Type
        event_type = request.headers.get("XF-Webhook-Event")
        if not event_type:
            # Fallback to payload data if header is missing
            event_type = request.data.get("event")
            
        if not event_type:
            return Response({"error": "Missing event type"}, status=400)

        # 3. Process the event asynchronously
        success = process_xf_webhook(event_type, request.data)
        
        if success:
            return Response({"status": "received", "event": event_type}, status=200)
        else:
            return Response({"status": "ignored", "event": event_type}, status=200)
