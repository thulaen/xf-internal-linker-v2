import networkit as nk
from django.test import SimpleTestCase

from apps.graph.services.signals.structural_embedding import (
    compute_embed_cosine,
    compute_structural_embeddings,
    populate_candidate_cosine,
)


class StructuralEmbeddingTests(SimpleTestCase):
    def test_structural_embedding_cosine(self):
        # Given two structurally-equivalent nodes, When embeddings are computed, 
        # Then their cosine is high (relative assertion, fixed seed).
        graph = nk.Graph(6, weighted=True, directed=False)
        # 1 and 2 are connected to 0 and 3
        graph.addEdge(0, 1, 1.0)
        graph.addEdge(0, 2, 1.0)
        graph.addEdge(3, 1, 1.0)
        graph.addEdge(3, 2, 1.0)
        # Extra nodes to pass the 5 node threshold
        graph.addEdge(0, 4, 1.0)
        graph.addEdge(3, 5, 1.0)
        
        embeddings = compute_structural_embeddings(graph)
        self.assertTrue(len(embeddings) > 0)
        
        vec1 = embeddings.get(1)
        vec2 = embeddings.get(2)
        vec0 = embeddings.get(0)
        
        self.assertIsNotNone(vec1)
        self.assertIsNotNone(vec2)
        self.assertIsNotNone(vec0)
        
        cos_1_2 = compute_embed_cosine(vec1, vec2)
        cos_1_0 = compute_embed_cosine(vec1, vec0)
        
        # 1 and 2 are structurally similar (they share all neighbors)
        self.assertGreater(cos_1_2, cos_1_0)

    def test_structural_embedding_skip_below_threshold(self):
        # Given a graph below the size threshold, When the signal runs, 
        # Then it is skipped cleanly.
        graph = nk.Graph(3, weighted=True, directed=False)
        graph.addEdge(0, 1, 1.0)
        graph.addEdge(1, 2, 1.0)
        
        embeddings = compute_structural_embeddings(graph)
        self.assertEqual(embeddings, {})

    def test_populate_candidate_cosine(self):
        embeddings = {
            10: [1.0, 0.0, 0.0],
            20: [0.0, 1.0, 0.0],
            30: [1.0, 0.0, 0.0],
        }
        id_to_idx = {"A": 10, "B": 20, "C": 30}
        
        candidates = [
            {"from_id": "A", "to_id": "B"},
            {"from_id": "A", "to_id": "C"},
            {"from_id": "A", "to_id": "MISSING"},
        ]
        
        populate_candidate_cosine(candidates, embeddings, id_to_idx)
        
        self.assertEqual(candidates[0]["embed_cosine"], 0.0)
        self.assertEqual(candidates[1]["embed_cosine"], 1.0)
        self.assertEqual(candidates[2]["embed_cosine"], 0.0)
