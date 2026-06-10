from rest_framework.views import APIView
from rest_framework.response import Response
from apps.platform.services.docs_search import federated_search

class FederatedSearchView(APIView):
    """
    GET /api/search/?q=<query>
    Returns combined search results from the internal application database
    and the Docusaurus documentation site.
    """
    permission_classes = [] # Adjust based on actual auth requirements

    def get(self, request, *args, **kwargs):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({
                "internal_results": [],
                "documentation_results": []
            })

        results = federated_search(query)
        return Response(results)
