# Pick #57 — Lexical Richness (TTR + Hapax Legomena Ratio)

## 1. Goal Description
Implement lexical richness metrics (Type-Token Ratio and Hapax Legomena ratio) to quantify the linguistic complexity and vocabulary diversity of content items.

## 2. User Review Required
> [!NOTE]
> These metrics are stored as metadata on `ContentItem` and can be used as features for future ranking signals (e.g., readability matching).

## 3. Math & Logic
- **Type-Token Ratio (TTR)**:
  $$TTR = \frac{|V|}{|N|}$$
  where $|V|$ is the number of unique tokens (types) and $|N|$ is the total number of tokens.
- **Hapax Legomena Ratio**:
  $$HapaxRatio = \frac{|V_{once}|}{|N|}$$
  where $|V_{once}|$ is the number of tokens that appear exactly once in the document.

## 4. Implementation
- Integrated into `NLPEnricher.enrich()`.
- Uses spaCy tokens (filtering punctuation and stop words).
- Results stored in `nlp_metadata` JSON field on `ContentItem`.

## 5. Verification Plan
- Unit tests in `test_nlp_enrichment.py` verifying ratios for known text samples.
- Empty text returns 0.0 for both.
