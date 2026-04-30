"""Suggestions URL routes — DRF router added in Phase 1."""

from django.urls import path

from .views import SuggestionReadinessView

urlpatterns = [
    path("readiness/", SuggestionReadinessView.as_view(), name="suggestion-readiness"),
]
