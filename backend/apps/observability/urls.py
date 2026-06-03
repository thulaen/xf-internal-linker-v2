from django.urls import path

from apps.observability.views import ObservabilityStackView

app_name = "observability"

urlpatterns = [
    path("stack/", ObservabilityStackView.as_view(), name="stack"),
]

