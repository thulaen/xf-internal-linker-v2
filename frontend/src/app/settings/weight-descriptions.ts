/**
 * Human-language descriptions for ranking weight keys.
 * Used by the weight diary timeline to narrate changes in plain English.
 */

export const WEIGHT_DESCRIPTIONS: Record<string, { name: string; what: string; highMeans: string; lowMeans: string }> = {
  semantic_similarity: {
    name: 'Semantic Similarity',
    what: 'How closely the topic of the source matches the destination.',
    highMeans: 'Only very closely related pages get linked.',
    lowMeans: 'Loosely related pages can get linked too.',
  },
  keyword_overlap: {
    name: 'Keyword Overlap',
    what: 'How many important words appear in both the source and destination.',
    highMeans: 'Links only between pages that share specific terms.',
    lowMeans: 'Term overlap matters less than topic similarity.',
  },
  node_affinity: {
    name: 'Link Graph Affinity',
    what: 'How close the pages are in the existing link structure.',
    highMeans: 'Prefers linking pages that are already structurally nearby.',
    lowMeans: 'Structural distance matters less.',
  },
  quality_score: {
    name: 'Page Quality',
    what: 'Engagement signals like views, replies, and freshness.',
    highMeans: 'Only high-traffic, actively-discussed pages become destinations.',
    lowMeans: 'Quieter pages can also receive links.',
  },
  explore_exploit: {
    name: 'Explore/Exploit Balance',
    what: 'Whether to favour proven links or try new combinations.',
    highMeans: 'More exploration — the system tries novel link pairings.',
    lowMeans: 'More exploitation — sticks with what has worked before.',
  },
  phrase_relevance: {
    name: 'Phrase Relevance',
    what: 'How well the anchor text matches a natural phrase in the sentence.',
    highMeans: 'Only very natural-sounding anchors are used.',
    lowMeans: 'Less-perfect anchor matches are accepted.',
  },
  diversity: {
    name: 'Slate Diversity',
    what: 'How much variety is enforced across suggestions for the same host.',
    highMeans: 'Suggestions are spread across different destinations.',
    lowMeans: 'Multiple suggestions can point to the same destination.',
  },
};
