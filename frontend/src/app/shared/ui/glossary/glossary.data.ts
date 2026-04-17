/**
 * Phase D2 / Gap 69 — Glossary entries shared by the Glossary drawer
 * and any future "explain this term" tooltips.
 *
 * Keep entries short (one or two sentences). Order doesn't matter —
 * the drawer alphabetizes for display. Adding new terms is the only
 * way the bank should ever change; removing a term breaks any
 * tooltip that still references it.
 */

export interface GlossaryEntry {
  term: string;
  definition: string;
  /** Optional category for grouping in the drawer. */
  category?:
    | 'ranking'
    | 'pipeline'
    | 'graph'
    | 'analytics'
    | 'health'
    | 'review'
    | 'general';
}

export const GLOSSARY: readonly GlossaryEntry[] = [
  {
    term: 'Anchor text',
    category: 'review',
    definition:
      'The clickable text of a hyperlink. Good anchors describe what the user will find on the other side.',
  },
  {
    term: 'Attribution',
    category: 'analytics',
    definition:
      'Crediting downstream outcomes (clicks, conversions) back to the link or content that drove them.',
  },
  {
    term: 'Backlink',
    category: 'graph',
    definition:
      'An inbound link to a page from somewhere else (internal or external). High-quality backlinks build authority.',
  },
  {
    term: 'Behavioral hub',
    category: 'graph',
    definition:
      'A cluster of pages that real users visit together in the same session. Strong signal of topical relatedness.',
  },
  {
    term: 'Broken link',
    category: 'health',
    definition:
      'A hyperlink whose target returns an error (4xx, 5xx) or never resolves. Hurts UX and SEO.',
  },
  {
    term: 'Candidate',
    category: 'ranking',
    definition:
      'A potential link suggestion before scoring. The pipeline produces many candidates per destination, then ranks them.',
  },
  {
    term: 'Co-occurrence',
    category: 'analytics',
    definition:
      "How often two pages are visited within the same user session. The dashboard's behavioral hubs are built from this.",
  },
  {
    term: 'Crawl',
    category: 'pipeline',
    definition:
      'Walking your site by following links to discover pages. Respects robots.txt and per-host rate limits.',
  },
  {
    term: 'Dead-end page',
    category: 'graph',
    definition:
      'A page with no outbound internal links. Visitors hit a wall and bounce.',
  },
  {
    term: 'Deep link',
    category: 'general',
    definition:
      "A URL that points directly to a specific section of a page (using a # fragment). The dashboard uses these for 'Go to' buttons.",
  },
  {
    term: 'Embedding',
    category: 'ranking',
    definition:
      'A list of numbers (typically 384 or 768) encoding the meaning of a piece of text so similar texts land near each other.',
  },
  {
    term: 'FAISS',
    category: 'ranking',
    definition:
      'A library for fast nearest-neighbor search on vectors. Powers the semantic similarity step of suggestion ranking.',
  },
  {
    term: 'Mission Brief',
    category: 'general',
    definition:
      'The three-sentence dashboard summary at the top: yesterday, today, and the most pressing issue.',
  },
  {
    term: 'Operator',
    category: 'general',
    definition:
      'The human running the system. The dashboard is designed for operators rather than end-readers.',
  },
  {
    term: 'Orphan page',
    category: 'graph',
    definition:
      'A page with no inbound internal links. Crawlers and users can\'t find it from anywhere on your site.',
  },
  {
    term: 'PageRank',
    category: 'graph',
    definition:
      'Link-based authority that flows through the link graph. Pages with many high-authority inbound links rank higher themselves.',
  },
  {
    term: 'Pipeline',
    category: 'pipeline',
    definition:
      'The end-to-end flow that turns raw content into ranked link suggestions: import → parse → embed → score → rank.',
  },
  {
    term: 'Precision',
    category: 'ranking',
    definition:
      "When the system makes a guess, how often it's right. High precision = few false positives.",
  },
  {
    term: 'Quarantine',
    category: 'pipeline',
    definition:
      'A failed job that the system isolated after repeated retries. Inspect, fix, then release back to the queue.',
  },
  {
    term: 'Rate limit',
    category: 'pipeline',
    definition:
      "Maximum requests per second the crawler is allowed to make against any one host. Set per-host so you don't hammer small servers.",
  },
  {
    term: 'Recall',
    category: 'ranking',
    definition:
      "Of all the right answers that exist, what fraction the system found. High recall = few missed opportunities.",
  },
  {
    term: 'Resume token',
    category: 'pipeline',
    definition:
      'Saved checkpoint state that lets a paused or crashed job pick up exactly where it left off.',
  },
  {
    term: 'Silo',
    category: 'graph',
    definition:
      'A topic cluster of related pages that cross-link to each other. Strong silos build topical authority.',
  },
  {
    term: 'Slate',
    category: 'ranking',
    definition:
      'The final ordered list of suggestions for one destination, after diversity rules have trimmed near-duplicates.',
  },
  {
    term: 'Stale data',
    category: 'health',
    definition:
      "Cached information older than the configured threshold. The dashboard flags it so you don't act on old numbers.",
  },
  {
    term: 'Suggestion',
    category: 'review',
    definition:
      'A proposed internal link from one page to another, with anchor text, confidence, and explainability metadata.',
  },
  {
    term: 'Throttle',
    category: 'general',
    definition:
      "Limit on how often an action can fire. The dashboard's snackbar throttle, for example, prevents toast floods.",
  },
  {
    term: 'Webhook',
    category: 'pipeline',
    definition:
      'An incoming HTTP POST that tells the system about an external event (e.g., a new XenForo post). Receipts are logged.',
  },
];
