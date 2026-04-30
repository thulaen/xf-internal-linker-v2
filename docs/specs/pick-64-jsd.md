# Pick #64 — Jensen-Shannon Divergence (Query Focus)

## 1. Goal Description
Implement Jensen-Shannon Divergence (JSD) to measure the alignment between the query distribution (source context) and the document distribution (destination). This rewards "focused" matches where the linguistic distribution of the anchor context aligns with the destination metadata.

## 2. Math & Logic
- **JSD**: Symmetrized and smoothed version of Kullback-Leibler divergence.
  $$JSD(P || Q) = \frac{1}{2} D(P || M) + \frac{1}{2} D(Q || M)$$
  where $M = \frac{1}{2}(P + Q)$.
- **Range**: [0, 1] (using base-2 logarithm).
- **Ranking Impact**: Bounded additive boost to `score_final`.
- **Default Weight**: 0.025 (Lin 1991).

## 3. Implementation
- Uses token distributions (unigrams) from source anchor context and destination title/keywords.
- Implemented in `ranker.py`.

## 4. Verification Plan
- Verify that identical distributions yield JSD=0 (maximal boost).
- Verify that completely disjoint distributions yield JSD=1 (zero boost).
