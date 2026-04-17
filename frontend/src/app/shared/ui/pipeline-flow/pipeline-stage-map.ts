/**
 * Phase MX2 / Gaps 295, 296, 297, 298, 305 — pipeline-stage metadata
 * shared across every "understand the pipeline" visual in the app.
 *
 * Single source of truth so the simplified architecture diagram, the
 * per-item journey animation, the color-coded row indicators, and the
 * live DAG view all agree on stage names, order, and tooltips.
 *
 * A stage lists its upstream dependencies so the DAG view can render
 * arrows without us hand-curating edge tuples per-component.
 */

export type PipelineStageId =
  | 'import'
  | 'normalize'
  | 'tokenize'
  | 'embed'
  | 'index'
  | 'candidates'
  | 'signals'
  | 'rerank'
  | 'diversity'
  | 'attribution'
  | 'publish';

export interface PipelineStageMeta {
  id: PipelineStageId;
  title: string;
  subtitle: string;          // one-sentence plain English
  tooltip: string;           // longer hover text
  icon: string;              // Material Icons ligature
  color: 'primary' | 'success' | 'info' | 'warning';
  upstream: PipelineStageId[];
}

export const PIPELINE_STAGES: readonly PipelineStageMeta[] = [
  {
    id: 'import',
    title: 'Import',
    subtitle: 'Pull new content from XenForo, WordPress, feeds, or uploads.',
    tooltip:
      'Fetches raw posts/pages into ContentItem rows. Skips items already synced with the same hash.',
    icon: 'download',
    color: 'primary',
    upstream: [],
  },
  {
    id: 'normalize',
    title: 'Normalize',
    subtitle: 'Strip junk HTML, canonicalise URLs, detect language.',
    tooltip:
      'Cleans up noisy imported markup so later stages see a consistent structure. Drops zero-content rows.',
    icon: 'auto_fix_high',
    color: 'primary',
    upstream: ['import'],
  },
  {
    id: 'tokenize',
    title: 'Tokenize',
    subtitle: 'Break text into words + sentences (spaCy / C++ fallback).',
    tooltip:
      'Uses the C++ texttok kernel when available — 6× faster than the Python fallback. See Performance Dashboard.',
    icon: 'short_text',
    color: 'info',
    upstream: ['normalize'],
  },
  {
    id: 'embed',
    title: 'Embed',
    subtitle: 'Compute 1024-d vectors with BGE-M3 (GPU preferred).',
    tooltip:
      'Generates pgvector embeddings for ContentItem + each sentence. Batched 32-at-a-time; falls back to CPU if GPU is absent.',
    icon: 'memory',
    color: 'info',
    upstream: ['tokenize'],
  },
  {
    id: 'index',
    title: 'Index',
    subtitle: 'Build the FAISS index for fast nearest-neighbour search.',
    tooltip:
      'Reloads the on-disk FAISS index when ≥1% of items changed. Otherwise reuses the cached index.',
    icon: 'grid_on',
    color: 'info',
    upstream: ['embed'],
  },
  {
    id: 'candidates',
    title: 'Candidates',
    subtitle: 'Shortlist host sentences + destination targets per item.',
    tooltip:
      'Cheap lexical + graph filters narrow the 100K×100K space to a few thousand pairs per item before ranking.',
    icon: 'filter_alt',
    color: 'primary',
    upstream: ['index'],
  },
  {
    id: 'signals',
    title: 'Signals',
    subtitle: 'Score each candidate on 23 ranking + value signals.',
    tooltip:
      'Each signal is computed under the Phase SEQ lock so they never fight for GPU. See Meta Algorithm Settings.',
    icon: 'analytics',
    color: 'info',
    upstream: ['candidates'],
  },
  {
    id: 'rerank',
    title: 'Rerank',
    subtitle: 'Apply learned weights + feedback loop to the slate.',
    tooltip:
      'Weights come from the monthly tuner. The feedback reranker uses recent approvals/rejections to nudge the order.',
    icon: 'sort',
    color: 'primary',
    upstream: ['signals'],
  },
  {
    id: 'diversity',
    title: 'Diversity',
    subtitle: 'Trim near-duplicate suggestions via MMR.',
    tooltip:
      'Slate diversity caps the number of suggestions that point to the same destination so the reviewer sees varied options.',
    icon: 'hub',
    color: 'primary',
    upstream: ['rerank'],
  },
  {
    id: 'attribution',
    title: 'Attribution',
    subtitle: 'Credit approved links back to the signals that picked them.',
    tooltip:
      'Runs periodically, not per-pipeline-pass. Drives the monthly weight tuner.',
    icon: 'account_tree',
    color: 'success',
    upstream: ['rerank'],
  },
  {
    id: 'publish',
    title: 'Publish',
    subtitle: 'Expose the survivors to the Review page.',
    tooltip:
      'Writes the Suggestion rows the reviewer sees. Past this point, nothing changes the slate until a new pipeline pass runs.',
    icon: 'publish',
    color: 'success',
    upstream: ['diversity', 'attribution'],
  },
] as const;

export function stageById(id: string): PipelineStageMeta | undefined {
  return PIPELINE_STAGES.find((s) => s.id === id);
}

export function stagesAfter(id: PipelineStageId): PipelineStageMeta[] {
  const idx = PIPELINE_STAGES.findIndex((s) => s.id === id);
  return idx < 0 ? [] : [...PIPELINE_STAGES.slice(idx + 1)];
}
