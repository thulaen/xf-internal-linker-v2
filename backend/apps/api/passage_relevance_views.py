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
        data = {}
        for key, typ in self.KEYS.items():
            row = AppSetting.objects.filter(key=key).first()
            if row and row.value:
                try:
                    if typ is bool:
                        val = row.value.strip().lower() == "true"
                    else:
                        val = typ(row.value)
                    data[key] = val
                    continue
                except ValueError:
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
