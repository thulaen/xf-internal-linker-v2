/**
 * Phase D2 / Gap 77 — Shared types for the "Explain this number" modal
 * and the `<app-explain-number>` button that opens it.
 *
 * Each metric the dashboard exposes can register its own derivation
 * (computed from X over Y), the formula (when applicable), the source
 * route, and a freshness note.
 */

export interface ExplainNumberInput {
  /** Short metric label, e.g. "Health Score". */
  label: string;
  /** Current numeric value as displayed. */
  value: string | number;
  /** One-sentence plain-English derivation (computed from X over Y). */
  derivation: string;
  /** Optional formula or pseudo-code shown in a monospace block. */
  formula?: string;
  /** Optional list of contributing parts ("warnings: 2 × -15 = -30"). */
  inputs?: readonly { name: string; value: string | number }[];
  /** When the value was generated, ISO timestamp. */
  generatedAt?: string | null;
  /** Optional source-of-truth route the user can drill into. */
  drillRoute?: string;
  drillLabel?: string;
}
