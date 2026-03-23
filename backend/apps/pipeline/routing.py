"""
WebSocket URL routing for the pipeline app.

Job progress events are pushed to the frontend via WebSocket,
eliminating the need for HTTP polling.

Channel URL patterns:
  ws://host/ws/jobs/<job_id>/  →  real-time job progress updates
"""

from django.urls import re_path

from .consumers import JobProgressConsumer

websocket_urlpatterns = [
    re_path(r"ws/jobs/(?P<job_id>[0-9a-f-]+)/$", JobProgressConsumer.as_asgi()),
]
