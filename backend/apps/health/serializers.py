from rest_framework import serializers
from .models import ServiceHealthRecord

# Config tier classification for grouping health cards in the UI.
# Maps service_key → tier.  Unlisted services default to 'optional'.
_CONFIG_TIER_MAP: dict[str, str] = {
    "database": "required_to_run",
    "redis": "required_to_run",
    "celery": "required_to_run",
    "celery_queues": "required_to_run",
    "celery_beat": "required_to_run",
    "disk_space": "required_to_run",
    "ml_models": "required_to_run",
    "native_scoring": "required_to_run",
    "xenforo": "required_for_sync",
    "wordpress": "required_for_sync",
    "sitemaps": "required_for_sync",
    "crawler_status": "required_for_sync",
    "crawler_storage": "required_for_sync",
    "ga4": "required_for_analytics",
    "gsc": "required_for_analytics",
    "matomo": "required_for_analytics",
}


class ServiceHealthRecordSerializer(serializers.ModelSerializer):
    config_tier = serializers.SerializerMethodField()

    class Meta:
        model = ServiceHealthRecord
        fields = [
            "service_key",
            "service_name",
            "service_description",
            "status",
            "status_label",
            "config_tier",
            "last_check_at",
            "last_success_at",
            "last_error_at",
            "last_error_message",
            "issue_description",
            "suggested_fix",
            "metadata",
        ]
        read_only_fields = fields

    def get_config_tier(self, obj: ServiceHealthRecord) -> str:
        return _CONFIG_TIER_MAP.get(obj.service_key, "optional")
