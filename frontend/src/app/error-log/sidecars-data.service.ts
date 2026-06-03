import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, of } from 'rxjs';

/**
 * Slice 1.6 — thin HTTP client for the Errors page sidecars tabs.
 *
 * The Django proxies live at:
 *   - GET /api/sidecars/snapshots/?issue_id=<int>
 *   - GET /api/sidecars/bulletins/?event_type=&min_severity=&limit=
 *
 * Both endpoints degrade to `status: 'sidecars_unavailable'` + empty
 * items when the Go binary is down, so the UI can keep its empty-state
 * placeholder instead of throwing a snackbar error.
 */

export interface SnapshotItem {
  id: string;
  issue_id: number;
  kind: string;
  category: string;
  schema_version: string;
  row_count: number;
  size_bytes: number;
  pinned: boolean;
  created_at_unix_nanos: number;
}

export interface BulletinItem {
  id: string;
  event_type: string;
  severity: string;
  message: string;
  context_json: string; // base64 bytes
  posted_at_unix_nanos: number;
  linked_autoissue_id: number;
}

export interface SidecarsResponse<T> {
  status: 'ok' | 'sidecars_unavailable';
  items: T[];
}

@Injectable({ providedIn: 'root' })
export class SidecarsDataService {
  private readonly http = inject(HttpClient);

  listSnapshots(issueId?: number): Observable<SidecarsResponse<SnapshotItem>> {
    const params = issueId ? `?issue_id=${issueId}` : '';
    return this.http
      .get<SidecarsResponse<SnapshotItem>>(`/api/sidecars/snapshots/${params}`)
      .pipe(catchError(() => of({ status: 'sidecars_unavailable' as const, items: [] })));
  }

  listBulletins(opts: {
    eventType?: string;
    minSeverity?: string;
    limit?: number;
  } = {}): Observable<SidecarsResponse<BulletinItem>> {
    const params = new URLSearchParams();
    if (opts.eventType) params.set('event_type', opts.eventType);
    if (opts.minSeverity) params.set('min_severity', opts.minSeverity);
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return this.http
      .get<SidecarsResponse<BulletinItem>>(`/api/sidecars/bulletins/${qs}`)
      .pipe(catchError(() => of({ status: 'sidecars_unavailable' as const, items: [] })));
  }

  /** Stream live bulletins via the existing RealtimeService topic. The
   * Channels bridge (apps.ops_feed.tasks.run_bullboard_bridge) publishes
   * `bullboard` topic events, so a consumer can call
   *   realtimeService.subscribeTopic<BulletinItem>('bullboard')
   * to receive a fresh BulletinItem each time bullboard.Post() fires. */
  static readonly LIVE_BULLETIN_TOPIC = 'bullboard';

  /** Same pattern for snapshot creation events when the consumer side ships. */
  static readonly LIVE_SNAPSHOT_TOPIC = 'snapshotd';
}
