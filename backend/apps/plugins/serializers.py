"""Serializers for the plugin system."""

from rest_framework import serializers

from .models import Plugin, PluginSetting


class PluginSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PluginSetting
        fields = ["id", "key", "value", "value_type", "description", "is_secret"]
        read_only_fields = ["id", "key", "value_type", "description"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.is_secret:
            data["value"] = "••••••••"
        return data


class PluginSerializer(serializers.ModelSerializer):
    settings = PluginSettingSerializer(many=True, read_only=True)

    class Meta:
        model = Plugin
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "version",
            "is_enabled",
            "is_installed",
            "module_path",
            "metadata",
            "settings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "slug",
            "description",
            "version",
            "is_installed",
            "module_path",
            "metadata",
            "created_at",
            "updated_at",
        ]
