# Pick #60 — MinHash + LSH (Lexical Near-Duplicate Detection)

## 1. Goal Description
Implement MinHash sketches to enable efficient lexical near-duplicate detection. This allows the system to identify content that is nearly identical even if minor edits exist.

## 2. Math & Logic
- **MinHash**: A technique for estimating Jaccard similarity between sets.
- **Sketch Size**: 128 hash functions (standard for balanced precision/performance).
- **LSH (Locality Sensitive Hashing)**: Groups items by their MinHash signatures to enable sub-linear time similarity search.
- **Citation**: Broder, A. Z. (1997). "On the resemblance and containment of documents."

## 3. Implementation
- Uses the `datasketch` library.
- Shingles: Words or character 5-grams.
- Integrated into `NLPEnricher.enrich()`.
- Signature (128 integers) stored in `nlp_metadata`.

## 4. Verification Plan
- Verify that identical documents produce identical signatures.
- Verify that near-duplicates (e.g., same text with one changed word) have high Jaccard similarity (> 0.9).
