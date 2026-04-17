/**
 * Phase D3 / Gap 176 — ELI5 ("Explain like I'm five") rotating concepts.
 *
 * Each entry rephrases an internal-linking concept the way you'd
 * explain it to a curious five-year-old. Distinct from the GLOSSARY
 * (precise definitions) and the daily quiz (interactive learning).
 */

export interface Eli5Snippet {
  id: string;
  topic: string;
  text: string;
}

export const ELI5: readonly Eli5Snippet[] = [
  { id: 'eli5-orphan', topic: 'Orphan page', text: 'Imagine a room in a house that has no door. Nobody can walk into it. An orphan page is like that — no other page on your site links to it.' },
  { id: 'eli5-anchor', topic: 'Anchor text', text: 'When you make something underlined and clickable, the words you choose are the anchor. Good anchors tell the reader what they\'ll find on the other side, like a sign on a door.' },
  { id: 'eli5-pagerank', topic: 'PageRank', text: 'Imagine pages voting for each other by linking. A page with many trusted votes ranks higher. PageRank is just the math of those votes.' },
  { id: 'eli5-embedding', topic: 'Embedding', text: 'A computer can\'t feel meaning, but it CAN compare numbers. An embedding turns a sentence into a list of numbers so the computer can spot two sentences that mean the same thing.' },
  { id: 'eli5-quarantine', topic: 'Quarantine', text: 'A job that keeps tripping over the same crack gets put aside in a "time-out" so it doesn\'t crash everything else. That\'s the quarantine.' },
  { id: 'eli5-stale', topic: 'Stale data', text: 'If you eat day-old bread it might still be okay, but a week-old loaf is risky. Stale data is the same — it might still work, but it\'s old enough that you should double-check before trusting it.' },
  { id: 'eli5-silo', topic: 'Silo', text: 'Group all your "cooking" pages together and have them link to each other a lot. That cluster is a silo. Search engines learn that you\'re an expert on cooking when your silo is tight.' },
  { id: 'eli5-confidence', topic: 'Confidence score', text: 'When the suggester says "I\'m 0.91 confident", it means out of 100 picks like this, about 91 are usually right. The closer to 1.0, the more sure it is.' },
];
