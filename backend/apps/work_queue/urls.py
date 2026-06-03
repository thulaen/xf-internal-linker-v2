from django.urls import path

from apps.work_queue.views import (
    WorkQueueCauseGroupsView,
    WorkQueueFeedView,
    WorkQueueOverviewView,
    WorkQueueSelfHealingApproveView,
    WorkQueueSelfHealingView,
    WorkQueueTaskClaimView,
    WorkQueueTaskRehearseView,
    WorkQueueTaskReleaseView,
)

app_name = "work_queue"

urlpatterns = [
    path("overview/", WorkQueueOverviewView.as_view(), name="overview"),
    path("feed/", WorkQueueFeedView.as_view(), name="feed"),
    path("cause-groups/", WorkQueueCauseGroupsView.as_view(), name="cause-groups"),
    path("tasks/<str:item_key>/claim/", WorkQueueTaskClaimView.as_view(), name="claim"),
    path("tasks/<str:item_key>/release/", WorkQueueTaskReleaseView.as_view(), name="release"),
    path("tasks/<str:item_key>/rehearse/", WorkQueueTaskRehearseView.as_view(), name="rehearse"),
    path("self-healing/", WorkQueueSelfHealingView.as_view(), name="self-healing"),
    path("self-healing/<int:decision_id>/approve/", WorkQueueSelfHealingApproveView.as_view(), name="self-healing-approve"),
]

