/**
 * Phase D3 — static content for the rotating dashboard cards.
 *
 * Each constant feeds one of the small "tip-style" cards:
 *   - WINS: Gap 159 — Latest Wins
 *   - AVOIDS: Gap 160 — Things to Avoid
 *   - PITFALLS: Gap 185 — Pitfall of the day
 *   - QUOTES: Gap 186 — Motivational quote
 *
 * Frontend-static so the cards work offline and render without any
 * backend dependency. Adding entries here is the only way these
 * lists grow; nothing is fetched at runtime.
 */

export interface ContentSnippet {
  id: string;
  text: string;
  /** Optional secondary line (attribution, source, follow-up). */
  attribution?: string;
}

export const WINS: readonly ContentSnippet[] = [
  { id: 'win-1', text: 'Approving in batches of 5 cuts review time by 40% on average.' },
  { id: 'win-2', text: "Behavioral hubs surface link opportunities you'd never find by topic alone." },
  { id: 'win-3', text: 'The C++ ranking hot-paths run 50× faster than the Python reference for big slates.' },
  { id: 'win-4', text: 'Stale-data warnings catch ~2% of suggestion errors before users see them.' },
  { id: 'win-5', text: 'Quarantined jobs auto-acknowledge after a successful retry — no extra clicks.' },
];

export const AVOIDS: readonly ContentSnippet[] = [
  { id: 'avoid-1', text: 'Don\'t delete alerts mid-sync — wait for the sync to complete or pause it first.' },
  { id: 'avoid-2', text: 'Avoid running the pipeline while a large import is in flight; queue contention will slow both.' },
  { id: 'avoid-3', text: "Don't disable the C++ scoring kernel in production unless you have a Python fallback warmed up." },
  { id: 'avoid-4', text: 'Resist editing weights without checking the recent challenger results first.' },
  { id: 'avoid-5', text: 'Avoid pasting raw API keys into the search bar — it logs to the audit trail.' },
];

export const PITFALLS: readonly ContentSnippet[] = [
  { id: 'pf-1', text: "If broken-link counts spike right after a sync, the source's CDN may be returning 503s — wait 10 minutes before re-scanning." },
  { id: 'pf-2', text: 'Pipeline runs that hang for >2h are usually waiting on the GPU to free — check Health → AI Models.' },
  { id: 'pf-3', text: 'Suggestion approval rates that drop overnight often mean a new content batch landed with bad anchors — sample one before approving en masse.' },
  { id: 'pf-4', text: "Embeddings stop refreshing if disk space drops below 10% — the dashboard's Health Score will go amber before this becomes red." },
  { id: 'pf-5', text: 'GA4 / GSC sync failures with auth errors usually mean the service-account key file expired or moved — check Settings → Connections.' },
  { id: 'pf-6', text: 'Setting the rate-limit too high on the crawler will trip your origin\'s WAF and ban your IP for hours.' },
  { id: 'pf-7', text: 'Don\'t pause the master switch for >24h — Celery beat schedules will queue up and stampede on resume.' },
];

export const QUOTES: readonly ContentSnippet[] = [
  { id: 'q-1', text: 'A daily review of pending suggestions beats a weekly review every time.', attribution: 'XF Linker handbook' },
  { id: 'q-2', text: 'Trust the dashboard, but verify the alert.', attribution: 'Operator wisdom' },
  { id: 'q-3', text: "Slow is smooth, smooth is fast.", attribution: 'Ops mantra' },
  { id: 'q-4', text: 'The best link is the one a reader actually clicks.', attribution: 'Internal linking proverb' },
  { id: 'q-5', text: 'Measure twice, deploy once.', attribution: 'Anonymous SRE' },
  { id: 'q-6', text: "If you can't explain the metric, you can't trust it.", attribution: 'Data-quality principle' },
  { id: 'q-7', text: 'A green dashboard is not the same as a working system — but it\'s a good start.', attribution: 'XF Linker' },
];
