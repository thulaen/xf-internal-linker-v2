"""
WSGI configuration for XF Internal Linker V2.

Used for standard HTTP deployments without WebSockets.
For production with WebSockets, use ASGI (asgi.py) instead.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_wsgi_application()
