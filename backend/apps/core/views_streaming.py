"""
Phase F1 / Gap 82 — Streamed HTML / SSE responses for long reports.

Django's default `JsonResponse` buffers the whole response before
sending. For a 10,000-row suggestion export that takes 8 seconds to
compute, the browser spins until the whole payload lands. Streaming
the response lets the browser render row-by-row and keeps the TCP
pipe warm so the request doesn't time out at intermediate proxies.

Two entry points:

  GET /api/reports/stream/suggestions/
      Chunked ``text/html`` stream. Useful for human-readable
      dashboards printed straight from the browser.

  GET /api/reports/stream/suggestions.sse
      Server-Sent Events stream (``text/event-stream``). Useful for
      long-running report generation where the frontend wants to
      show progress.

The bodies here intentionally use small synthetic iterators. A
future session can swap in ``Suggestion.objects.iterator()`` + the
explainability joins once the report shape stabilises.
"""

from __future__ import annotations

import time
from typing import Iterable, Iterator

from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


class StreamedSuggestionsHtmlView(APIView):
    """GET /api/reports/stream/suggestions/

    Returns a chunked ``text/html`` response that flushes one row at
    a time. The browser renders progressively so the first rows are
    visible almost immediately.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return StreamingHttpResponse(
            self._stream_html(),
            content_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    def _stream_html(self) -> Iterator[bytes]:
        yield b"<!doctype html><html><head><title>Suggestions report</title></head><body>\n"
        yield b"<h1>Suggestions report</h1><ol>\n"
        for row in self._rows():
            yield (f"<li>{row}</li>\n").encode("utf-8")
        yield b"</ol></body></html>\n"

    def _rows(self) -> Iterable[str]:
        # Placeholder — swap to real queryset iteration once the
        # report shape is finalised (reuses Suggestion + explainer).
        for i in range(1, 51):
            yield f"Row {i}"


class StreamedSuggestionsSseView(APIView):
    """GET /api/reports/stream/suggestions.sse

    Returns a ``text/event-stream`` response. Each SSE event is
    prefixed with ``data: `` and terminated with ``\\n\\n``.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        response = StreamingHttpResponse(
            self._stream_sse(),
            content_type="text/event-stream; charset=utf-8",
        )
        # SSE needs no intermediate buffering.
        response["Cache-Control"] = "no-store"
        response["X-Accel-Buffering"] = "no"
        return response

    def _stream_sse(self) -> Iterator[bytes]:
        # Start event for client-side state initialisation.
        yield b"event: start\ndata: {}\n\n"
        for i in range(1, 51):
            payload = f'{{"index":{i},"message":"Row {i}"}}'
            yield f"event: row\ndata: {payload}\n\n".encode("utf-8")
            # Placeholder for real work; remove/replace in production.
            time.sleep(0.02)
        yield b"event: end\ndata: {}\n\n"
