/**
 * Phase D3 / Gap 177 — FAQ entries for the drawer.
 *
 * Operator-grade FAQ — focuses on workflow questions, not feature
 * tutorials. Add entries as common support questions emerge.
 */

export interface FaqEntry {
  id: string;
  question: string;
  answer: string;
}

export const FAQ: readonly FaqEntry[] = [
  {
    id: 'faq-where-start',
    question: 'I just logged in. Where should I start?',
    answer: 'Open the dashboard. The Mission Brief at the top tells you yesterday/today/what-to-watch in three sentences. Then work through the daily pre-flight checklist (Alerts → Health → Preview → Review → Broken-link scan).',
  },
  {
    id: 'faq-suggestion-blocked',
    question: 'A suggestion looks wrong — can I block it?',
    answer: 'Open the Review queue, click the suggestion, then "Reject" with a reason. The reasons feed the auto-tuner so similar suggestions are scored down in the future.',
  },
  {
    id: 'faq-pipeline-stuck',
    question: 'The pipeline says "running" for hours — is it stuck?',
    answer: 'A pipeline run that exceeds its expected duration usually means a sub-stage hit a network failure. Open Jobs, find the run, and check the per-stage progress. If everything is at 100% but the run hasn\'t closed, click Restart on the relevant job.',
  },
  {
    id: 'faq-broken-after-sync',
    question: 'Broken-link count spiked right after a sync — bad news?',
    answer: "Usually no. The new content brought in fresh outbound links, some of which the source server may be returning 5xx for temporarily (CDN warmup, rate limiting). Wait 10 minutes and re-run the broken-link scan before triaging.",
  },
  {
    id: 'faq-pause-vs-stop',
    question: 'Pause vs Emergency Stop — what\'s the difference?',
    answer: 'Pause stops new tasks at the next safe checkpoint and lets in-flight work finish. Emergency Stop pauses AND clears the queue — use only when something is actively damaging data.',
  },
  {
    id: 'faq-master-pause',
    question: 'I clicked the master pause and now everything is stuck — how do I recover?',
    answer: 'Click the same button again to resume. Beat-scheduled tasks that piled up while paused will fire on the next interval; if your queue was paused for >24h, expect a brief stampede of catch-up jobs.',
  },
  {
    id: 'faq-weight-tuning',
    question: 'Should I edit ranking weights manually?',
    answer: 'Almost never. The auto-tuner runs monthly and proposes challenger weights based on real reviewer feedback. Manual edits skip the safety review and can break ranking quality. If you do edit, save a preset first so you can roll back.',
  },
  {
    id: 'faq-noob-mode',
    question: 'What\'s "Noob mode" hiding from me?',
    answer: 'Noob mode hides advanced controls (raw SQL editors, kernel-level toggles, plugin internals). Pro mode reveals everything. The split is per-component; switching modes never deletes data.',
  },
  {
    id: 'faq-export-data',
    question: 'How do I get data out of this thing?',
    answer: 'Most data tables have a download icon (⬇) in the top-right that exports CSV or JSON. For full database snapshots, use Settings → Export.',
  },
  {
    id: 'faq-shortcuts',
    question: 'What keyboard shortcuts exist?',
    answer: 'Press ? anywhere to see the full cheatsheet. Common ones: Ctrl+K (or ⌘K) opens the command palette; Alt+G opens the glossary; Esc returns you to the dashboard from any non-form page.',
  },
];
