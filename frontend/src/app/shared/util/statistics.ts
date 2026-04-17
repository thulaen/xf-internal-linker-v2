/**
 * Phase MX3 / Gap 348 — Statistical significance helper.
 *
 * Pure utility consumed by the Baseline Indicator (Gap 347), the
 * "Are we on track?" meter (Gap 349), and the seasonality comparator
 * (Gap 350). Intentionally minimal — no numeric library, no crypto.
 */

export interface SignificanceVerdict {
  /** How many standard deviations the point is from the baseline. */
  z: number;
  /** True when |z| >= 2 (rough 95% confidence under a normal assumption). */
  significant: boolean;
  /** "above" / "below" / "within" — consumed directly by chip labels. */
  direction: 'above' | 'below' | 'within';
  /** Plain-English marker for the UI ("↑ 2.3σ above baseline"). */
  marker: string;
}

export function mean(values: readonly number[]): number {
  if (values.length === 0) return 0;
  let sum = 0;
  for (const v of values) sum += v;
  return sum / values.length;
}

export function stddev(values: readonly number[]): number {
  if (values.length < 2) return 0;
  const μ = mean(values);
  let sq = 0;
  for (const v of values) sq += (v - μ) ** 2;
  return Math.sqrt(sq / (values.length - 1));
}

/**
 * Gap 348 — is the current value significantly different from baseline?
 */
export function significanceOf(
  current: number,
  baseline: readonly number[],
): SignificanceVerdict {
  const μ = mean(baseline);
  const σ = stddev(baseline);
  if (σ === 0) {
    return {
      z: 0,
      significant: false,
      direction: 'within',
      marker: 'baseline flat — no signal',
    };
  }
  const z = (current - μ) / σ;
  const direction: 'above' | 'below' | 'within' =
    Math.abs(z) < 2 ? 'within' : z > 0 ? 'above' : 'below';
  const sigma = Math.abs(z).toFixed(1);
  const marker =
    direction === 'within'
      ? 'within noise'
      : direction === 'above'
        ? `↑ ${sigma}σ above baseline`
        : `↓ ${sigma}σ below baseline`;
  return {
    z,
    significant: Math.abs(z) >= 2,
    direction,
    marker,
  };
}

/**
 * Gap 347 — compact summary string for a baseline indicator chip.
 *   "Typical: 120 – 180 (μ=150)"
 */
export function baselineRangeLabel(baseline: readonly number[]): string {
  if (baseline.length === 0) return 'No baseline yet';
  const μ = mean(baseline);
  const σ = stddev(baseline);
  const low = Math.round(μ - σ);
  const high = Math.round(μ + σ);
  return `Typical: ${low.toLocaleString()} – ${high.toLocaleString()} (μ=${Math.round(μ).toLocaleString()})`;
}
