# Pick #63 — TextRank (Extractive Summary)

## 1. Goal Description
Implement an extractive summarization service using the TextRank algorithm to generate concise summaries (1-3 sentences) for content items, used in UI previews and as condensed inputs for reranking.

## 2. Math & Logic
- **Graph Construction**: Sentences as nodes, similarity as weighted edges.
- **Similarity**: Cosine similarity between sentence embeddings (reusing BGE-M3 vectors).
- **Ranking**: Apply PageRank on the sentence similarity graph.
- **Selection**: Top-N sentences by PageRank score.
- **Citation**: Mihalcea, R., & Tarau, P. (2004). "TextRank: Bringing Order into Text."

## 3. Implementation
- Uses `networkx` for PageRank.
- Uses spaCy for sentence splitting.
- Summary stored in `nlp_metadata` (or separate `summary` field).

## 4. Verification Plan
- Verify that for a long article, the generated summary contains representative key sentences.
- Verify performance on very long documents (use truncation if necessary).
