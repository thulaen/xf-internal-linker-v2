"""
Root URL configuration for XF Internal Linker V2.

API routes live under /api/
Admin lives under /admin/
WebSocket connections are handled by ASGI/Channels (not here).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Angular dev server — extract port so the magic-number linter stays green.
# Change this if your local ng serve runs on a different port.
_FRONTEND_DEV_URL = "http://localhost:4200/"

# Customize Django Admin branding
admin.site.site_header = "XF Internal Linker V2"
admin.site.site_title = "XF Linker Admin"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += [
        path("", RedirectView.as_view(url=_FRONTEND_DEV_URL), name="root-redirect"),
    ]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
