"""Passage relevance views module for the api app."""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.core.models import AppSetting
from apps.suggestions.recommended_weights import recommended_bool, recommended_float, recommended_int

class PassageRelevanceSettingsView(APIView):
    """Settings view for Passage Relevance (Group E)."""
    
    permission_classes = [IsAuthenticated]

    KEYS = {
        "passage_relevance.enabled": bool,
        "passage_relevance.passage_words": int,
        "passage_relevance.passages_per_page_max": int,
        "passage_relevance.ranking_weight": float,
    }

    def get(self, request):
        # Refactor 2026-05-04: previously this issued FOUR separate
        # SELECT queries (one per AppSetting key inside the loop).
        # Replaced with a single bulk fetch — N times faster.
        rows = {
            row.key: row.value
            for row in AppSetting.objects.filter(key__in=list(self.KEYS.keys()))
        }
        data: dict[str, object] = {}
        for key, typ in self.KEYS.items():
            raw = rows.get(key)
            if raw:
                try:
                    if typ is bool:
                        data[key] = raw.strip().lower() == "true"
                    else:
                        data[key] = typ(raw)
                    continue
                except ValueError:
                    # Bad row value falls through to the recommended-
                    # defaults block below; the operator's malformed
                    # setting is not allowed to break the page.
                    pass

            # Fallbacks
            try:
                if typ is bool:
                    data[key] = recommended_bool(key)
                elif typ is int:
                    data[key] = recommended_int(key)
                else:
                    data[key] = recommended_float(key)
            except KeyError:
                if key == "passage_relevance.enabled":
                    data[key] = True
                elif key == "passage_relevance.passage_words":
                    data[key] = 200
                elif key == "passage_relevance.passages_per_page_max":
                    data[key] = 0
                elif key == "passage_relevance.ranking_weight":
                    data[key] = 0.05

        return Response(data)

    def post(self, request):
        for key, typ in self.KEYS.items():
            if key in request.data:
                val = request.data[key]
                if val is None:
                    AppSetting.objects.filter(key=key).delete()
                else:
                    AppSetting.objects.update_or_create(
                        key=key,
                        defaults={"value": str(val)}
                    )
        return self.get(request)
