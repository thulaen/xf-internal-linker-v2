import { ErrorLogEntry, NodeSummary } from './diagnostics.service';

/**
 * Error Log types + pure helpers extracted from `diagnostics.component.ts`
 * so the component stays under the 500-line file-length hook. The component
 * wraps these with thin getters/methods so its template bindings
 * (`groupedErrors`, `uniqueNodes()`, `trackGroupFingerprint`, etc.) keep
 * working unchanged.
 *
 * Pure by design: no component state, no DI, no side effects.
 */

/**
 * A fingerprint-grouped bucket of errors rendered as a single row in the
 * Error Log. The representative row carries the display fields; totalCount
 * is the sum of `occurrence_count` across the bucket so the UI can show
 * an accurate multiplier badge without scanning the list every render.
 */
export interface ErrorGroup {
  fingerprint: string;
  representative: ErrorLogEntry;
  totalCount: number;
}

/**
 * Bucket the unack'd error list by fingerprint, optionally filtering to a
 * single node first. The caller passes `errors` and `filterNodeId` so this
 * remains pure and independent of component lifecycle.
 */
export function groupErrors(
  errors: ErrorLogEntry[],
  filterNodeId: string | null,
): ErrorGroup[] {
  const filtered = filterNodeId
    ? errors.filter(e => e.node_id === filterNodeId)
    : errors;

  const buckets = new Map<string, ErrorLogEntry[]>();
  for (const e of filtered) {
    const key = e.fingerprint ?? `unique-${e.id}`;
    const existing = buckets.get(key);
    if (existing) {
      existing.push(e);
    } else {
      buckets.set(key, [e]);
    }
  }

  const result: ErrorGroup[] = [];
  buckets.forEach((entries, fingerprint) => {
    // Sum occurrence_count across bucket, defaulting to entries.length
    // when a row is missing the field (old snapshots).
    const totalCount = entries.reduce(
      (sum, e) => sum + (e.occurrence_count ?? 1),
      0,
    );
    result.push({
      fingerprint,
      representative: entries[0],
      totalCount,
    });
  });
  return result;
}

/** Unique node ids seen in the current error list — powers the filter
 *  chip bar. Returned in first-seen order so the chip layout is stable
 *  across re-renders. */
export function uniqueNodeIds(errors: ErrorLogEntry[]): string[] {
  const seen: string[] = [];
  const set = new Set<string>();
  for (const e of errors) {
    const id = e.node_id;
    if (id && !set.has(id)) {
      set.add(id);
      seen.push(id);
    }
  }
  return seen;
}

/** Peak value in a 7-day sparkline — used to scale bar heights. Floor
 *  of 1 so the bars never `Infinity / 0`. */
export function maxTrendCount(trend: { count: number }[] | undefined): number {
  if (!trend || trend.length === 0) return 1;
  return Math.max(1, ...trend.map(t => t.count));
}

/** Other errors within the ±5-minute window the backend pre-computed.
 *  Constrained to the current unack list so acknowledged rows don't
 *  appear as "related" noise. */
export function relatedErrors(
  e: ErrorLogEntry,
  errors: ErrorLogEntry[],
): ErrorLogEntry[] {
  const ids = new Set(e.related_error_ids ?? []);
  if (ids.size === 0) return [];
  return errors.filter(x => ids.has(x.id));
}

/** Text-only ISO date rendered in sparkline tooltip. Split so the HTML
 *  template stays lean and the slice matches exactly one bar. */
export function trendLabel(trend: { date: string; count: number }[] | undefined): string {
  if (!trend || trend.length === 0) return '';
  return `Last 7 days: total ${trend.reduce((s, t) => s + t.count, 0)}`;
}

export function trackGroupFingerprint(_index: number, group: ErrorGroup): string {
  return group.fingerprint;
}

export function trackErrorId(_index: number, error: ErrorLogEntry): number {
  return error.id;
}

export function trackNodeId(_index: number, node: NodeSummary): string {
  return node.node_id;
}

export function trackTrendDate(_index: number, point: { date: string }): string {
  return point.date;
}

/**
 * GT-G2 — build an AI-ready prompt for an error entry. Pure — returns the
 * prompt string. Clipboard I/O and the snackbar confirmation stay in the
 * component so this module has no DOM dependency. An engineer can paste
 * the result into Claude/Codex/ChatGPT with no additional context.
 */
export function buildAIPromptForError(e: ErrorLogEntry): string {
  const ctx = e.runtime_context ?? {};
  const lines: string[] = [];
  lines.push('## Error Report');
  lines.push(`**Job:** ${e.job_type} · ${e.step}`);
  lines.push(`**Node:** ${e.node_id ?? 'unknown'} (${e.node_role ?? 'unknown'})`);
  lines.push(`**Severity:** ${e.severity ?? 'medium'}`);
  lines.push(`**What happened:** ${e.error_message}`);
  if (e.why) lines.push(`**Why:** ${e.why}`);
  if (e.how_to_fix) lines.push(`**Suggested fix:** ${e.how_to_fix}`);
  lines.push(
    `**Runtime at time of error:** GPU=${ctx.gpu_available ? 'yes' : 'no'} · ` +
      `embedding=${ctx.embedding_model ?? 'unknown'} · ` +
      `spaCy=${ctx.spacy_model ?? 'missing'} · ` +
      `python=${ctx.python_version ?? 'unknown'}`,
  );
  if (e.raw_exception) {
    lines.push('', '**Traceback:**', '```', e.raw_exception, '```');
  }
  if (e.glitchtip_url) {
    lines.push('', `**GlitchTip:** ${e.glitchtip_url}`);
  }
  return lines.join('\n');
}

export interface ErrorSnapshotDiff {
  unack: ErrorLogEntry[];
  ack: ErrorLogEntry[];
  priorityArrival: ErrorLogEntry | null;
}

/**
 * Pure part of the 30-second error-log poll. Splits the incoming snapshot
 * into unack + ack lists and picks the highest-priority new critical/high
 * arrival (for the Scroll-to-Attention pulse). The caller is responsible
 * for the side effects (setting component state, triggering the pulse).
 */
export function diffErrorSnapshot(
  previous: ErrorLogEntry[],
  next: ErrorLogEntry[],
): ErrorSnapshotDiff {
  const previousIds = new Set(previous.map(e => e.id));
  const unack = next.filter(e => !e.acknowledged);
  const ack = next.filter(e => e.acknowledged);

  const arrivals = unack.filter(
    e =>
      !previousIds.has(e.id) &&
      (e.severity === 'critical' || e.severity === 'high'),
  );
  const priorityArrival =
    arrivals.find(e => e.severity === 'critical') ?? arrivals[0] ?? null;

  return { unack, ack, priorityArrival };
}
