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
from apps.realtime.routing import websocket_urlpatterns as realtime_ws  # noqa: E402
from config.websocket_token_auth import QueryStringTokenAuthMiddleware  # noqa: E402

# OpenTelemetry ASGI middleware — wraps the HTTP app so every uvicorn
# request becomes a trace span with method, route, status, latency, and
# DB / Redis / outbound HTTP children. The DjangoInstrumentor in
# `config.settings.base` produces sparse spans on uvicorn (ASGI) — this
# wrapper fills the gap. No-op import if the package isn't installed
# (test runners that skip the OTel deps still work).
try:
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    django_asgi_app = OpenTelemetryMiddleware(django_asgi_app)
except ImportError:
    pass

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                QueryStringTokenAuthMiddleware(
                    URLRouter(
                        pipeline_ws + notifications_ws + realtime_ws,
                    )
                )
            )
        ),
    }
)
