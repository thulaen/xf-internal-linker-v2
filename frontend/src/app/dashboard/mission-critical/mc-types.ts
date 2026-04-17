/**
 * Phase MC — Mission Critical tab shared types.
 * Matches `apps.diagnostics.views.MissionCriticalView` exactly.
 */

export type McTileState =
  | 'WORKING'
  | 'IDLE'
  | 'PAUSED'
  | 'DEGRADED'
  | 'FAILED';

export interface McTile {
  id: string;
  name: string;
  state: McTileState;
  plain_english: string;
  last_action_at: string | null;
  progress: number | null;
  actions: string[];
  group: 'algorithms' | null;
  root_cause: string | null;
  // Phase MX1 — Gap 255 ETA, 257 uptime, 261 retry count, 262 health grade,
  // 265 silent-since timestamp, 256 last-action subtitle.
  eta_seconds?: number | null;
  uptime_pct_24h?: number | null;
  retry_count_since_success?: number | null;
  health_grade?: 'A' | 'B' | 'C' | 'D' | 'F' | null;
  silent_since?: string | null;
  last_action_label?: string | null;
  downstream_impact?: string[];
  kernel_names?: string[];
}

export interface McPayload {
  tiles: McTile[];
  updated_at: string;
}
