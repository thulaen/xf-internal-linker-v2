/**
 * Phase D3 / Gap 187 — Frontend-static changelog feed.
 *
 * Each entry has an ISO date and a short user-facing description.
 * The "What's new since your last login" card filters this list by
 * the timestamp stored in `xfil_last_visit` (set by the personal-bar
 * component) and shows entries newer than that.
 *
 * Adding entries here is the only way the changelog grows. Future
 * sessions can swap in a backend feed by changing the importer; the
 * card consumes the same `ChangelogEntry[]` shape either way.
 */

export interface ChangelogEntry {
  /** ISO date — first second of the day is fine. */
  date: string;
  /** Short label, e.g. "Phase D3 ships". */
  title: string;
  /** One- or two-sentence summary of what changed for the operator. */
  body: string;
  /** Optional link target (deep-link to the affected feature). */
  route?: string;
}

export const CHANGELOG: readonly ChangelogEntry[] = [
  {
    date: '2026-04-17T00:00:00Z',
    title: 'Phase D3 — Dashboard noob KISS extensions',
    body:
      '36 dashboard improvements: clock + greeting bar, "you are here" strip, big-icon launcher grid, instant-health weather card, sync-activity widget, daily-goal tracker, FAQ drawer, motivational quote, and more. See the dashboard for everything new.',
    route: '/dashboard',
  },
  {
    date: '2026-04-16T00:00:00Z',
    title: 'Phase D2 — Dashboard noob UX (gaps 66-78)',
    body:
      'Operator pre-flight checklist, one-button reset, glossary drawer (Alt+G), guided tour, noob/pro toggle, daily tips, behavioural nudge, escape hatch, read-aloud, weekly digest opt-in, explain-this-number modal, and a help chatbot.',
    route: '/dashboard',
  },
  {
    date: '2026-04-15T00:00:00Z',
    title: 'Phase D1 — Dashboard noob UX (gaps 53-65)',
    body:
      'Mission Brief, Status Story, Priority Action Queue, Health Score Dial, Trend Deltas, Color Legend, Tutorial Mode, Explain Mode, daily quiz, and the priority summary bell all landed.',
    route: '/dashboard',
  },
  {
    date: '2026-04-14T00:00:00Z',
    title: 'Phase E2 — Cross-cutting polish (gaps 40-52)',
    body:
      'Skip-to-content link, session-timeout warning with extension, 429 Retry-After countdown toast, dialog↔URL routing, CSV/JSON export menu, char-counter directive, web-vitals telemetry, and connection-aware loading.',
  },
];
