/**
 * Phase OF — Operations Feed shared types.
 *
 * Matches `apps.ops_feed.serializers.OperationEventSerializer`. Keep in
 * sync with that serializer — a missing field here would silently drop
 * from the feed.
 */

export type OpsEventSeverity = 'info' | 'warning' | 'error' | 'success';

export interface OpsEvent {
  id: number;
  timestamp: string;
  event_type: string;
  source: string;
  plain_english: string;
  severity: OpsEventSeverity;
  related_entity_type: string;
  related_entity_id: string;
  runtime_context: Record<string, unknown>;
  occurrence_count: number;
  error_log_id: number | null;
}

/** Client-side dedup window — matches backend 60s but applied to
 *  consecutive rows in the rendered list so rapid repeats collapse
 *  visually even before the backend finalises the merge. */
export const OPS_FEED_VISUAL_DEDUP_WINDOW_MS = 60_000;

export const OPS_FEED_MAX_ROWS = 500;
