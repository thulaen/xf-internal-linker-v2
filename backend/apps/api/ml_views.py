"""
Stateless ML endpoints for C# worker compute dependencies.

These endpoints provide advanced NLP (spaCy) and sentence embedding
capabilities to the C# HttpWorker without tightly coupling the orchestrator
to Python state or persistence. 

They do NOT touch the database or hold any runtime orchestration logic.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.pipeline.services.distiller import distill_body
from apps.pipeline.services.embeddings import _load_model, _get_model_name, _get_batch_size, _l2_normalize

class MLDistillView(APIView):
    """
    POST /api/ml/distill/
    Accepts: { "sentences": ["...", "..."], "max_sentences": int (optional) }
    Returns: { "distilled": "..." }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        sentences = request.data.get("sentences", [])
        if not isinstance(sentences, list):
            return Response({"error": "'sentences' must be a list of strings."}, status=status.HTTP_400_BAD_REQUEST)
            
        max_sentences = int(request.data.get("max_sentences", 5))
        
        try:
            distilled_text = distill_body(sentences, max_sentences=max_sentences)
            return Response({"distilled": distilled_text})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MLEmbedView(APIView):
    """
    POST /api/ml/embed/
    Accepts: { "texts": ["...", "..."] }
    Returns: { "embeddings": [[0.1, ...], ...] }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        texts = request.data.get("texts", [])
        if not isinstance(texts, list):
            return Response({"error": "'texts' must be a list of strings."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not texts:
            return Response({"embeddings": []})
            
        try:
            model_name = _get_model_name()
            model = _load_model(model_name)
            batch_size = _get_batch_size()
            
            raw_vectors = model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            
            # Normalize for cosine similarity operations
            vectors = _l2_normalize(raw_vectors)
            
            return Response({"embeddings": vectors.tolist()})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
