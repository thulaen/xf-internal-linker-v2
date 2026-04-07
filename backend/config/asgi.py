"""
ASGI configuration for XF Internal Linker V2.

Handles both:
- HTTP requests → Django views
- WebSocket connections → Django Channels (real-time job progress)
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Initialize Django ASGI app early to ensure settings are loaded
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.notifications.routing import websocket_urlpatterns as notifications_ws  # noqa: E402
from apps.pipeline.routing import websocket_urlpatterns as pipeline_ws  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    pipeline_ws + notifications_ws,
                )
            )
        ),
    }
)
