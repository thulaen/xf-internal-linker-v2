/**
 * Group M.1 — Admin Models page service.
 *
 * Thin wrapper around the existing
 * ``/api/settings/runtime/models/`` endpoints (already shipped in
 * ``backend/apps/core/views_runtime_registry.py``). The endpoints
 * return one envelope per task-type ("embedding", "classifier",
 * etc) describing every registered model + every placement
 * (primary executor or helper PC) so the operator can see at a
 * glance who is the active champion, who the candidate, what
 * disk we can reclaim, and what the most recent audit-log entries
 * are. Action buttons map to ``POST /<id>/action/`` with one of
 * ``download | warm | pause | resume | promote | rollback | drain``.
 */
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type RuntimeModelTaskType = 'embedding' | 'classifier' | 'reranker' | 'kg';

export type RuntimeModelRole =
  | 'champion'
  | 'candidate'
  | 'shadow'
  | 'archived'
  | 'retired';

export type RuntimeModelStatus =
  | 'registered'
  | 'downloading'
  | 'ready'
  | 'warming'
  | 'paused'
  | 'draining'
  | 'failed'
  | 'retired';

export type RuntimeModelAction =
  | 'download'
  | 'warm'
  | 'pause'
  | 'resume'
  | 'promote'
  | 'rollback'
  | 'drain';

/** One row in the response's ``active_model`` / ``candidate_model`` field. */
export interface RuntimeModel {
  id: number;
  task_type: RuntimeModelTaskType;
  model_name: string;
  model_family: string;
  dimension: number | null;
  device_target: string;
  batch_size: number;
  memory_profile: Record<string, unknown>;
  role: RuntimeModelRole;
  status: RuntimeModelStatus;
  health_result: Record<string, unknown>;
  algorithm_version: string;
  promoted_at: string | null;
  draining_since: string | null;
  last_warmup_result: Record<string, unknown>;
}

/** One row in the response's ``placements`` array. */
export interface RuntimeModelPlacement {
  id: number;
  registry_id: number;
  model_name: string;
  role: RuntimeModelRole;
  executor_type: 'primary' | 'helper';
  helper_id: number | null;
  helper_name: string;
  artifact_path: string;
  disk_bytes: number;
  status: string;
  last_used_at: string | null;
  warmed_at: string | null;
  last_error: string;
  deletable: boolean;
}

/** One audit-log entry in ``recent_audit_log``. */
export interface RuntimeAuditEntry {
  id: number;
  created_at: string;
  action: string;
  subject_type: string;
  subject_id: string;
  actor: string;
  message: string;
  metadata: Record<string, unknown>;
}

/** Backfill plan summary (when one is in flight). */
export interface RuntimeBackfillPlan {
  id: number;
  from_model_id: number | null;
  to_model_id: number | null;
  status: string;
  compatibility_status: string;
  progress_pct: number;
  checkpoint: Record<string, unknown>;
  last_error: string;
}

/** Full registry summary as returned by the backend. */
export interface RuntimeModelsSummary {
  task_type: RuntimeModelTaskType;
  active_model: RuntimeModel | null;
  candidate_model: RuntimeModel | null;
  placements: RuntimeModelPlacement[];
  reclaimable_disk_bytes: number;
  backfill: RuntimeBackfillPlan | null;
  device: string;
  hot_swap_safe: boolean;
  master_paused: boolean;
  recent_audit_log: RuntimeAuditEntry[];
  last_audit_at: string | null;
}

/**
 * Action endpoint response — small status object (NOT the full
 * summary envelope). Shape varies by action: ``promote`` adds
 * ``dimension_changed``, ``rollback`` adds ``model_name``,
 * ``download`` adds ``placement_id``. The caller refreshes the
 * full summary after a successful action.
 */
export interface RuntimeActionResponse {
  status: string;
  dimension_changed?: boolean;
  model_name?: string;
  placement_id?: number;
}

/** Placement-delete response — ``deleted: true`` + reclaimed bytes. */
export interface RuntimePlacementDeleteResponse {
  deleted: boolean;
  reclaimed_disk_bytes: number;
}

@Injectable({ providedIn: 'root' })
export class RuntimeModelsService {
  private http = inject(HttpClient);
  private base = '/api/settings/runtime/models/';

  /** Fetch the full per-task-type registry envelope. */
  list(taskType: RuntimeModelTaskType): Observable<RuntimeModelsSummary> {
    return this.http.get<RuntimeModelsSummary>(this.base, {
      params: { task_type: taskType },
    });
  }

  /**
   * Fire one of the seven supported actions against a registered
   * model. ``placement_id`` is optional — it scopes the action to
   * one specific placement when supplied (e.g. drain just the
   * helper-PC placement, leave the primary alone). Returns a small
   * status object; the caller should refresh the full summary.
   */
  action(
    modelId: number,
    action: RuntimeModelAction,
    placementId?: number,
  ): Observable<RuntimeActionResponse> {
    const body: Record<string, unknown> = { action };
    if (placementId !== undefined) {
      body['placement_id'] = placementId;
    }
    return this.http.post<RuntimeActionResponse>(`${this.base}${modelId}/action/`, body);
  }

  /** Delete a placement (only ``deletable: true`` placements). */
  deletePlacement(placementId: number): Observable<RuntimePlacementDeleteResponse> {
    return this.http.delete<RuntimePlacementDeleteResponse>(
      `${this.base}placements/${placementId}/`,
    );
  }
}
