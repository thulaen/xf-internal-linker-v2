/**
 * Tailwind config — Angular CDK + Tailwind stack (no third-party UI lib).
 *
 * `preflight: false` keeps Tailwind's reset off so utilities coexist with the
 * remaining Angular Material during the migration.
 *
 * The theme maps our existing CSS design tokens (defined in
 * `src/styles/_theme-vars.scss`) into Tailwind, so components write clean
 * token-backed utilities like `bg-surface`, `text-primary`, `rounded-card`,
 * `text-warning-dark` — never hardcoded hex, never long `var()` arbitrary
 * values. The CSS tokens remain the single source of truth; this just exposes
 * them to Tailwind. Spacing/font-size use Tailwind's defaults, which already
 * sit on the 4px grid (p-4 = 16px, p-6 = 24px, gap-4 = 16px, etc.).
 */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        primary: 'var(--color-primary)',
        'primary-dark': 'var(--color-primary-dark)',
        'blue-50': 'var(--color-blue-50)',
        success: 'var(--color-success)',
        'success-dark': 'var(--color-success-dark)',
        warning: 'var(--color-warning)',
        'warning-dark': 'var(--color-warning-dark)',
        error: 'var(--color-error)',
        'error-dark': 'var(--color-error-dark)',
        surface: 'var(--color-bg-white)',
        page: 'var(--color-bg-page)',
        faint: 'var(--color-bg-faint)',
        border: 'var(--color-border)',
        'text-primary': 'var(--color-text-primary)',
        'text-secondary': 'var(--color-text-secondary)',
        'text-muted': 'var(--color-text-muted)',
        'on-dark': 'var(--color-text-on-dark)',
        // GSC-measured series colours (metric tiles, charts, table numbers).
        'series-clicks': 'var(--series-clicks)',
        'series-impressions': 'var(--series-impressions)',
        'series-indexed': 'var(--series-indexed)',
        'series-grey': 'var(--series-not-indexed)',
      },
      borderRadius: {
        card: 'var(--card-border-radius)', // 12px — GSC-measured
        pill: 'var(--radius-pill)',
      },
    },
  },
  plugins: [],
};
