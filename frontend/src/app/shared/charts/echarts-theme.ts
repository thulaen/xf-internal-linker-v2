/**
 * ECharts theme + token helpers (Slice 15 / Phase 6).
 *
 * Apache ECharts replaced chart.js + d3 across the app. ECharts needs raw
 * colour strings (it cannot read `var(--token)` the way SCSS can), so this
 * module resolves the design-system CSS variables from the live DOM once and
 * caches them. The colours therefore still flow from the single source of
 * truth (`_theme-vars.scss`) — never hardcoded hex in a component.
 *
 * Design-system rules honoured:
 *  - GSC blue `var(--color-primary)` is the primary series colour.
 *  - Flat colours only (no gradients).
 *  - No orange — the warning swatch uses the tokened `--color-warning-accent`.
 *
 * The cache is invalidated on first read after a theme change would be rare
 * (the app has one theme), so a simple module-level cache is enough. Tests
 * that run without a DOM fall back to the literal token defaults below.
 */

/** Fallback values mirror `_theme-vars.scss` for non-DOM (unit-test) runs. */
const TOKEN_FALLBACKS: Record<string, string> = {
  '--color-primary': '#4285f4',
  '--color-text-secondary': '#3c4043',
  '--color-text-muted': '#5f6368',
  '--color-border': '#dadce0',
  '--color-border-faint': '#f1f3f4',
  '--color-success': '#228747',
  '--color-error': '#e81403',
  '--color-warning-accent': '#fbbc04',
  '--series-clicks': '#4285f4',
  '--series-impressions': '#5e35b1',
  '--series-indexed': '#00897b',
  '--series-not-indexed': '#80868b',
  '--graph-node-orphan': '#e81403',
};

let cache: Record<string, string> | null = null;

/** Read a single design-system colour token (cached after first DOM read). */
export function token(name: string): string {
  if (!cache) {
    cache = {};
  }
  if (cache[name]) {
    return cache[name];
  }
  let value = '';
  if (typeof document !== 'undefined' && document.documentElement) {
    value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  const resolved = value || TOKEN_FALLBACKS[name] || '#80868b';
  cache[name] = resolved;
  return resolved;
}

/** Drop the cache — used by tests that swap tokens between specs. */
export function clearTokenCache(): void {
  cache = null;
}

/** Convert a hex colour + alpha (0..1) to an `rgba()` string for soft fills. */
export function withAlpha(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  if (clean.length !== 6) {
    return hex;
  }
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * The shared GA4/GSC base for every chart: tokened axis text, faint grid,
 * dark tooltip, system font. Spread this into each `EChartsOption` and add
 * the series-specific bits. Keeps all 13 charts visually consistent.
 */
export function gscChartBase(): Record<string, unknown> {
  const textMuted = token('--color-text-muted');
  const gridFaint = withAlpha(textMuted, 0.1);
  return {
    textStyle: {
      fontFamily:
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif",
      color: token('--color-text-secondary'),
    },
    tooltip: {
      backgroundColor: 'rgba(32, 33, 36, 0.92)',
      borderWidth: 0,
      padding: 12,
      textStyle: { color: '#e8eaed', fontSize: 12 },
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: textMuted, fontSize: 12 },
    },
    grid: {
      left: 8,
      right: 16,
      bottom: 36,
      top: 16,
      containLabel: true,
    },
    _gridFaint: gridFaint,
  };
}

/**
 * Categorical palette used for pies and multi-series bars. Tokened, flat,
 * no orange (warning slot uses the accent yellow token). Order is stable so
 * series colours don't jump between renders.
 */
export function gscPalette(): string[] {
  return [
    token('--color-primary'),
    token('--series-indexed'),
    token('--color-warning-accent'),
    token('--color-error'),
    token('--series-impressions'),
    token('--series-not-indexed'),
  ];
}
