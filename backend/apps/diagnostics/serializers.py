from rest_framework import serializers
from .models import ServiceStatusSnapshot, SystemConflict
from apps.audit.models import ErrorLog


class ServiceStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatusSnapshot
        fields = "__all__"


class SystemConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConflict
        fields = "__all__"


class ErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorLog
        fields = "__all__"
