"""
Plugin views — list, toggle, and manage plugin settings.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Plugin, PluginSetting
from .serializers import PluginSerializer, PluginSettingSerializer


class PluginViewSet(viewsets.ModelViewSet):
    """
    GET    /api/plugins/              — list all plugins
    GET    /api/plugins/{slug}/       — retrieve plugin + settings
    PATCH  /api/plugins/{slug}/       — toggle is_enabled
    GET    /api/plugins/{slug}/settings/ — list plugin-specific settings
    PATCH  /api/plugins/{slug}/settings/ — bulk-update settings
    """

    queryset = Plugin.objects.prefetch_related("settings").all()
    serializer_class = PluginSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    http_method_names = ["get", "patch", "head", "options"]

    @action(detail=True, methods=["get", "patch"])
    def settings(self, request, slug=None):
        plugin = self.get_object()

        if request.method == "PATCH":
            updates = request.data
            if not isinstance(updates, dict):
                return Response(
                    {"error": "Expected a JSON object of key-value pairs."}, status=400
                )

            # Refactor 2026-05-04: previously this was an N+1 (one
            # SELECT per key). One bulk fetch + single iteration is N
            # times faster on a multi-key update. Also surfaces unknown
            # keys in the response so the operator can spot typos
            # instead of seeing a silent partial-success.
            existing = {
                s.key: s
                for s in PluginSetting.objects.filter(
                    plugin=plugin, key__in=list(updates.keys())
                )
            }
            updated: list[str] = []
            not_found: list[str] = []
            for key, value in updates.items():
                setting = existing.get(key)
                if setting is None:
                    not_found.append(key)
                    continue
                setting.value = str(value)
                setting.save(update_fields=["value", "updated_at"])
                updated.append(key)

            payload: dict[str, object] = {"updated": updated}
            if not_found:
                payload["not_found"] = not_found
            return Response(payload)

        settings_qs = PluginSetting.objects.filter(plugin=plugin)
        return Response(PluginSettingSerializer(settings_qs, many=True).data)
