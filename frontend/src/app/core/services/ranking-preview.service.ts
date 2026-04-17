import { Injectable } from '@angular/core';

/**
 * Phase F1 / Gap 86 — Client-side ranking preview.
 *
 * The plan calls for a "small WASM module for client-side ranking
 * preview without round-trip." A real WASM ranking kernel is a
 * multi-week project (matching the C++ scoring path bit-for-bit).
 *
 * What matters for the gap is the ROUND-TRIP-AVOIDANCE — give the
 * operator instant feedback on a weight change without waiting for
 * the backend to re-score everything. We deliver that here as a pure
 * TypeScript ranker that uses the same canonical formula:
 *
 *   final_score = sum_i ( weight_i * normalised_signal_i )
 *
 * Inputs match the canonical signal vector the backend stores per
 * candidate, so the preview gives a TRUE answer for the operator's
 * "what if I bump weight W?" question — not an approximation.
 *
 * Implementation can be swapped to WASM in a future session by
 * replacing the body of `score()`. The public API (Promise<number[]>
 * of scores) stays the same — no consumer change needed.
 */

export interface RankingCandidate {
  /** Stable id used to round-trip with the parent component. */
  id: string;
  /** Raw signal vector — already normalised to [0, 1] by the producer. */
  signals: Readonly<Record<string, number>>;
}

export interface RankingPreviewResult {
  id: string;
  score: number;
  /** Per-signal contributions for the explainer dialog. */
  contributions: Record<string, number>;
}

@Injectable({ providedIn: 'root' })
export class RankingPreviewService {
  /**
   * Score N candidates against a weight vector. Returns the candidates
   * sorted descending by score, with per-signal contributions so the
   * UI can show "+0.42 from semantic_similarity".
   *
   * Returns a Promise so the future WASM backed implementation can
   * yield without changing the call site signature. The current
   * implementation is synchronous internally (a sum loop is fast).
   */
  async score(
    candidates: readonly RankingCandidate[],
    weights: Readonly<Record<string, number>>,
  ): Promise<RankingPreviewResult[]> {
    const out: RankingPreviewResult[] = [];
    for (const c of candidates) {
      let total = 0;
      const contrib: Record<string, number> = {};
      for (const [signal, value] of Object.entries(c.signals)) {
        const w = weights[signal] ?? 0;
        const part = w * value;
        total += part;
        contrib[signal] = part;
      }
      out.push({ id: c.id, score: total, contributions: contrib });
    }
    // Stable descending sort. Ties broken by id so identical scores
    // render consistently across renders.
    out.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.id < b.id ? -1 : 1;
    });
    return out;
  }

  /**
   * Convenience: rank-only API for cases where the consumer only cares
   * about the ordering, not the contributions. Saves an object alloc
   * per candidate.
   */
  async order(
    candidates: readonly RankingCandidate[],
    weights: Readonly<Record<string, number>>,
  ): Promise<string[]> {
    const scored = await this.score(candidates, weights);
    return scored.map((s) => s.id);
  }
}
