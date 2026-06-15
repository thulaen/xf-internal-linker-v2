/**
 * Plain-English tooltips + spec-file pointers for meta-algorithm cards
 * on the Settings page.
 *
 * Single source of truth for two related concerns:
 *   1. The hover-tooltip shown on each card title (Group A.4 of the
 *      masterplan).
 *   2. The spec-file slug used by the "View spec" button to open
 *      docs/specs/<slug>.md inside a Material dialog (Group A.5).
 *
 * Keep both in one file so a vibe coder can add or change a meta-algo
 * helper with a single edit. No component-code changes required when
 * a new meta-algo lands — register here, drop a `[matTooltip]` and a
 * "View spec" button on the card, done.
 */

export interface MetaAlgoHelper {
  /** One-line plain-English description shown on title hover. */
  readonly tooltip: string;
  /**
   * Slug of the spec file inside `docs/specs/` (no `.md` suffix).
   * The backend `/api/docs/specs/<slug>/` endpoint resolves the
   * full filename via an allow-list. Keep slugs `^[a-z0-9-]+$`.
   */
  readonly specSlug: string;
}

export const META_ALGO_HELPERS: Record<string, MetaAlgoHelper> = {
  // FR-099 Dangling Authority Redistribution Bonus
  darb: {
    tooltip: $localize`:@@metaAlgorithms.darb.tip:DARB: Boosts pages from highly-trusted sites that barely link out, so their authority does not get lost in dead-end pages. Source: FR-099 spec.`,
    specSlug: 'fr099-dangling-authority-redistribution-bonus',
  },

  // FR-100 Katz Marginal Information Gain
  kmig: {
    tooltip: $localize`:@@metaAlgorithms.kmig.tip:KMIG: Adds a small bonus to suggested links that introduce a fresh topic the host page has not covered yet. Source: FR-100 spec.`,
    specSlug: 'fr100-katz-marginal-information-gain',
  },

  // FR-101 Tarjan Articulation Point Boost
  tapb: {
    tooltip: $localize`:@@metaAlgorithms.tapb.tip:TAPB: Boosts pages that act as the only bridge between two parts of the site so they stay reachable. Source: FR-101 spec.`,
    specSlug: 'fr101-tarjan-articulation-point-boost',
  },

  // FR-102 K-Core Integration Boost
  kcib: {
    tooltip: $localize`:@@metaAlgorithms.kcib.tip:KCIB: Boosts pages that sit deep inside a dense cluster of related pages (well-integrated content). Source: FR-102 spec.`,
    specSlug: 'fr102-kcore-integration-boost',
  },

  // FR-103 Bridge-Edge Redundancy Penalty
  berp: {
    tooltip: $localize`:@@metaAlgorithms.berp.tip:BERP: Slightly penalises suggestions that would pile yet another link across an already-over-used bridge between page clusters. Source: FR-103 spec.`,
    specSlug: 'fr103-bridge-edge-redundancy-penalty',
  },

  // FR-104 Host-Graph Topic Entropy Boost
  hgte: {
    tooltip: $localize`:@@metaAlgorithms.hgte.tip:HGTE: Boosts host pages that touch many different topics, so suggestions for those hosts stay diverse instead of repetitive. Source: FR-104 spec.`,
    specSlug: 'fr104-host-graph-topic-entropy-boost',
  },

  // FR-105 Reverse Search-Query Vocabulary Alignment
  rsqva: {
    tooltip: $localize`:@@metaAlgorithms.rsqva.tip:RSQVA: Aligns suggestions with the actual Google-search vocabulary your readers use, so links match what real visitors are searching for. Source: FR-105 spec.`,
    specSlug: 'fr105-reverse-search-query-vocabulary-alignment',
  },

  // FR-260 Time-as-Operator Spectral Decay
  tosd: {
    tooltip: $localize`:@@metaAlgorithms.tosd.tip:TOSD: Rewards links to structurally stable, long-lived pages and ignores short-lived attention spikes (a time-based spectral filter). Source: FR-260 spec.`,
    specSlug: 'fr260-tosd',
  },

  // FR-261 Directed Sequential Transition Probability
  dstp: {
    tooltip: $localize`:@@metaAlgorithms.dstp.tip:DSTP: Rewards links that follow the real forward path users click from one page to the next. Source: FR-261 spec.`,
    specSlug: 'fr261-dstp',
  },

  // FR-262 In-Community Popularity Contrast
  icpc: {
    tooltip: $localize`:@@metaAlgorithms.icpc.tip:ICPC: Rewards "local hero" pages that are highly referenced inside their own topic community even if they are not globally popular. Source: FR-262 spec.`,
    specSlug: 'fr262-icpc',
  },

  // FR-263 Stochastic Block Model Affinity
  sbma: {
    tooltip: $localize`:@@metaAlgorithms.sbma.tip:SBMA: Rewards links that follow the site's natural structural roles (which kinds of pages usually link to which kinds). Source: FR-263 spec.`,
    specSlug: 'fr263-sbma',
  },

  // FR-264 Riemannian Geodesic Semantic Distance
  rgsd: {
    tooltip: $localize`:@@metaAlgorithms.rgsd.tip:RGSD: Measures the true curved semantic distance between two pages instead of a flat straight-line distance. Source: FR-264 spec.`,
    specSlug: 'fr264-rgsd',
  },

  // FR-265 Cross-Silo Bridging Reward
  csbr: {
    tooltip: $localize`:@@metaAlgorithms.csbr.tip:CSBR: Rewards links that bridge two different content silos when the two pages share a strong topic overlap. Source: FR-265 spec.`,
    specSlug: 'fr265-csbr',
  },
};

/**
 * Backwards-compat alias for the original shape (`META_ALGO_TOOLTIPS`).
 * Components written before A.5 may still import the flat tooltip map;
 * keep it working by deriving from the richer helper map. No duplication
 * of copy.
 */
export const META_ALGO_TOOLTIPS: Record<string, string> = Object.fromEntries(
  Object.entries(META_ALGO_HELPERS).map(([key, helper]) => [key, helper.tooltip]),
);

/** Tooltip getter — empty string for unknown keys so matTooltip renders nothing. */
export function metaAlgoTip(key: string): string {
  return META_ALGO_HELPERS[key]?.tooltip ?? '';
}

/** Spec-slug getter — empty string for unknown keys (caller should hide the View spec button). */
export function metaAlgoSpecSlug(key: string): string {
  return META_ALGO_HELPERS[key]?.specSlug ?? '';
}

/** Pretty-name getter for the dialog title (uppercased key). */
export function metaAlgoPrettyName(key: string): string {
  return key.toUpperCase();
}
