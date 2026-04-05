"""Core URL routes — system status only."""

from django.urls import path
from .views import HealthCheckView

urlpatterns = [
    path("system/health/", HealthCheckView.as_view(), name="health-check"),
]
