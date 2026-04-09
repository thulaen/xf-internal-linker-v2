"""
Sync app views — content import endpoints.
"""

import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.decorators import action
from .models import SyncJob, WebhookReceipt
from .serializers import SyncJobSerializer, WebhookReceiptSerializer

from apps.api.throttles import ImportTriggerThrottle as _ImportTriggerThrottle


ALLOWED_MODES = {"full", "titles", "quick"}
MAX_UPLOAD_MB = 200


class ImportUploadView(APIView):
    """Accept a JSONL export file from the user's browser and start an import job."""

    parser_classes = [MultiPartParser]
    throttle_classes = [_ImportTriggerThrottle]

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

        # ── Sample-validate the first 10 JSONL lines ──────────────
        import json as _json

        validation_errors: list[str] = []
        try:
            file_obj.seek(0)
            for line_num, raw_line in enumerate(file_obj, 1):
                if line_num > 10:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    item = _json.loads(line)
                except _json.JSONDecodeError as exc:
                    validation_errors.append(f"Line {line_num}: Invalid JSON — {exc}")
                    continue

                if not item.get("scope_id"):
                    validation_errors.append(f"Line {line_num}: Missing 'scope_id'")
                if not (
                    item.get("content_id")
                    or item.get("thread_id")
                    or item.get("resource_id")
                ):
                    validation_errors.append(
                        f"Line {line_num}: Missing 'content_id'/'thread_id'/'resource_id'"
                    )
                if not item.get("title"):
                    validation_errors.append(f"Line {line_num}: Missing 'title'")
                if not (item.get("url") or item.get("view_url")):
                    validation_errors.append(
                        f"Line {line_num}: Missing 'url' or 'view_url'"
                    )

            file_obj.seek(0)  # rewind for the actual save below
        except Exception:
            pass  # file-read errors will surface during the real import

        if validation_errors:
            return Response(
                {
                    "error": f"Validation failed ({len(validation_errors)} errors in first 10 lines):",
                    "details": validation_errors,
                },
                status=400,
            )

        # Save to BASE_DIR/data/imports/
        imports_dir = Path(settings.BASE_DIR) / "data" / "imports"
        imports_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid.uuid4().hex}.jsonl"
        dest_path = imports_dir / safe_name
        with open(dest_path, "wb") as fh:
            for chunk in file_obj.chunks():
                fh.write(chunk)

        job = SyncJob.objects.create(
            source="jsonl", mode=mode, file_name=file_obj.name, status="pending"
        )
        job_id = str(job.job_id)

        from apps.pipeline.tasks import dispatch_import_content

        dispatch_import_content(
            mode=mode,
            source="jsonl",
            file_path=str(dest_path),
            job_id=job_id,
            force_reembed=bool(request.data.get("force_reembed") or False),
        )

        return Response(
            {
                "job_id": job_id,
                "file": file_obj.name,
                "mode": mode,
            },
            status=202,
        )


class SyncJobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing synchronization jobs (imports).
    """

    queryset = SyncJob.objects.all()
    serializer_class = SyncJobSerializer
    pagination_class = None
    lookup_field = "job_id"

    @action(detail=False, methods=["get"])
    def source_status(self, request):
        """
        GET /api/sync-jobs/source_status/

        Returns unified health status for XF and WP sources.
        """
        from apps.health.models import ServiceHealthRecord

        xf_status = ServiceHealthRecord.objects.filter(service_key="xenforo").first()
        wp_status = ServiceHealthRecord.objects.filter(service_key="wordpress").first()

        return Response(
            {
                "api": xf_status.status == ServiceHealthRecord.STATUS_HEALTHY
                if xf_status
                else False,
                "wp": wp_status.status == ServiceHealthRecord.STATUS_HEALTHY
                if wp_status
                else False,
            }
        )

    @action(detail=False, methods=["post"])
    def trigger_full_run(self, request):
        """
        One-button workflow: Sync all sources + crawl + pipeline.
        Dispatches the orchestrator Celery task.
        """
        from apps.crawler.tasks import orchestrate_full_run

        orchestrate_full_run.apply_async(queue="pipeline")
        return Response(
            {"status": "queued", "message": "Full sync, crawl, and pipeline started."}
        )

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

        job = SyncJob.objects.create(source=source, mode=mode, status="pending")
        job_id = str(job.job_id)

        from apps.pipeline.tasks import dispatch_import_content

        dispatch_import_content(
            mode=mode,
            source=source,
            scope_ids=scope_ids,
            job_id=job_id,
            force_reembed=bool(request.data.get("force_reembed") or False),
        )

        return Response(
            {
                "job_id": job_id,
                "source": source,
                "mode": mode,
            },
            status=202,
        )


class WebhookReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing webhook audit logs.
    """

    queryset = WebhookReceipt.objects.all()
    serializer_class = WebhookReceiptSerializer
    pagination_class = None
    lookup_field = "receipt_id"


class _WebhookRateThrottle(AnonRateThrottle):
    """60 requests/minute per IP — protects against webhook flood attacks."""

    rate = "60/min"


class XenForoWebhookView(APIView):
    """
    Real-time webhook receiver for XenForo forum events.
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [_WebhookRateThrottle]

    def post(self, request):
        from .services.webhooks import verify_xf_signature, process_xf_webhook

        signature = request.headers.get("XF-Webhook-Secret")
        if not verify_xf_signature(signature):
            return Response({"error": "Invalid webhook secret"}, status=403)

        event_type = request.headers.get("XF-Webhook-Event") or request.data.get(
            "event"
        )
        if not event_type:
            return Response({"error": "Missing event type"}, status=400)

        success = process_xf_webhook(event_type, request.data)
        return Response(
            {"status": "received" if success else "ignored", "event": event_type},
            status=200,
        )


class WordPressWebhookView(APIView):
    """
    Real-time webhook receiver for WordPress post updates.

    POST /api/v1/sync/webhooks/wordpress/
    """

    permission_classes = []
    authentication_classes = []
    throttle_classes = [_WebhookRateThrottle]

    def post(self, request):
        from .services.webhooks import verify_wp_signature, process_wp_webhook

        # Security: we use X-Wp-Webhook-Secret or simple body field
        signature = request.headers.get("X-Wp-Webhook-Secret") or request.data.get(
            "secret"
        )
        if not verify_wp_signature(signature):
            return Response({"error": "Invalid webhook secret"}, status=403)

        event_type = request.data.get("event", "wp_update")
        success = process_wp_webhook(event_type, request.data)
        return Response(
            {"status": "received" if success else "ignored", "event": event_type},
            status=200,
        )
