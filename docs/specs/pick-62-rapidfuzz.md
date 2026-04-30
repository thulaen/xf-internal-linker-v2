# Pick #62 — RapidFuzz Fuzzy Anchor Matching

## 1. Goal Description
Implement fuzzy string matching for anchor discovery to reward anchors that are "close enough" to target phrases (e.g., handling typos or minor variations) during the discovery and ranking stages.

## 2. Math & Logic
- **Metric**: Token Set Ratio (RapidFuzz).
  $$Score = Ratio(Anchor, Phrase)$$
- **Ranking Impact**: Bounded additive boost to `score_final`.
- **Default Weight**: 0.015 (Joachims 2007).
- **Neutral Fallback**: 0.0 (if ratio is below threshold, e.g., 85%).

## 3. Implementation
- Integrated into `ranker.py` / `phrase_matching.py`.
- Threshold-gated to avoid noise.

## 4. Verification Plan
- Verify that "internal linker" matches "internal linkr" with a high score.
- Verify that unrelated strings have 0.0 contribution.
