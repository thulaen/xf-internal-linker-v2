/**
 * Phase MX3 / Gap 350 — Seasonality-aware comparisons.
 *
 * Pure helper that picks the right historical point to compare "today"
 * against, depending on the day of week + whether a week-ago baseline
 * is available.
 *
 * Rule:
 *   • default → same-day-last-week (Tue vs last Tue) so you avoid
 *     week-over-week noise from weekend traffic dips
 *   • weekend → same-day-last-week (Sat vs last Sat)
 *   • fallback when <1 week of history → yesterday
 */

export interface SeasonalComparison {
  /** Index into the caller-supplied series (0 = most recent/today). */
  compareIndex: number | null;
  /** Human-readable label for chip display. */
  label: string;
}

/**
 * @param series newest-first array of numeric points.
 */
export function pickSeasonalComparison(
  series: readonly number[],
): SeasonalComparison {
  if (series.length === 0) {
    return { compareIndex: null, label: 'no history' };
  }
  // A week is 7 days. Pick 7 indices back if available.
  if (series.length > 7) {
    return { compareIndex: 7, label: 'vs same day last week' };
  }
  if (series.length >= 2) {
    return { compareIndex: 1, label: 'vs yesterday' };
  }
  return { compareIndex: null, label: 'no baseline yet' };
}

/**
 * Convenience: compute the delta + label for a daily-newest-first
 * series. Returns `{delta, label}` or null when no baseline exists.
 */
export function seasonalDelta(
  series: readonly number[],
): { delta: number; delta_pct: number; label: string } | null {
  const pick = pickSeasonalComparison(series);
  if (pick.compareIndex === null || pick.compareIndex >= series.length) {
    return null;
  }
  const today = series[0] ?? 0;
  const compare = series[pick.compareIndex] ?? 0;
  const delta = today - compare;
  const delta_pct = compare === 0 ? 0 : (delta / compare) * 100;
  return { delta, delta_pct, label: pick.label };
}
