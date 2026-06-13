from django.urls import path

from apps.observability.views import ObservabilityStackView, PrometheusSummaryView

app_name = "observability"

urlpatterns = [
    path("stack/", ObservabilityStackView.as_view(), name="stack"),
    # Live metric snapshot fetched from VictoriaMetrics. Used by the Angular
    # Prometheus tab to show real numbers (request rate, p95 latency, etc.)
    # without the browser needing to talk to VictoriaMetrics directly.
    path("prometheus-summary/", PrometheusSummaryView.as_view(), name="prometheus-summary"),
]

