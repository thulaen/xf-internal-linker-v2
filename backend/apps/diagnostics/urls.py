from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'services', views.ServiceStatusViewSet, basename='service-status')
router.register(r'conflicts', views.ConflictViewSet, basename='conflict')
router.register(r'errors', views.SystemErrorViewSet, basename='system-error')

urlpatterns = [
    path('', include(router.urls)),
    path('overview/', views.DiagnosticsOverviewView.as_view(), name='diagnostics-overview'),
    path('features/', views.FeatureReadinessView.as_view(), name='feature-readiness'),
    path('resources/', views.ResourceUsageView.as_view(), name='resource-usage'),
    path('weights/', views.WeightDiagnosticsView.as_view(), name='weight-diagnostics'),
    path('internal/scheduler/dispatch/', views.SchedulerDispatchView.as_view(), name='scheduler-dispatch'),
]
