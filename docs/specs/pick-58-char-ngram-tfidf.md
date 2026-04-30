# Pick #58 — Char n-gram (3-5) Hashed TF-IDF

## 1. Goal Description
Implement sub-word level features using hashed character n-grams. This provides robustness against typos and morphological variations by capturing overlapping character sequences.

## 2. Math & Logic
- **Features**: Character n-grams of length 3, 4, and 5.
- **Dimensionality**: 256-dimensional vector (fixed size for performance).
- **Hashing**: Use `sklearn.feature_extraction.text.HashingVectorizer` with `analyzer='char'` and `ngram_range=(3, 5)`.
- **Normalization**: L2 normalization of the resulting vector.

## 3. Implementation
- Integrated into `NLPEnricher.enrich()`.
- Uses a `HashingVectorizer(n_features=256, analyzer='char', ngram_range=(3, 5))`.
- Vector stored as `pgvector(256)` on `ContentItem` (requires migration).

## 4. Verification Plan
- Verify that similar words (e.g., "internal" vs "interal") produce vectors with high cosine similarity.
- Verify 256 dimensions are correctly persisted.
