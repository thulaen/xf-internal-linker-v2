import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpClient } from '@angular/common/http';
import { catchError, of } from 'rxjs';

/**
 * Phase OB / Gaps 131 + 132 — Feature flags + A/B harness.
 *
 * Combines into one service because every A/B test IS a feature flag
 * with variants. Backend-authoritative: the server decides which flag
 * is active and which variant a given user lands in. Frontend caches
 * the answer in memory + localStorage so the first frame after
 * app-boot doesn't flicker with the default variant.
 *
 * Contract:
 *   GET /api/feature-flags/
 *     → [{ key: string, enabled: bool, variant?: string }]
 *
 * Until the backend endpoint ships, every call returns the fallback
 * set (empty — everything disabled). Components MUST treat the flag
 * value as a runtime check, not a build-time constant.
 *
 * Usage:
 *
 *   constructor(private flags: FeatureFlagsService) {}
 *
 *   showBetaCard = computed(() => this.flags.isEnabled('beta-card'));
 *
 *   buttonVariant = computed(() => this.flags.variantOf('cta-copy'));
 *
 *   // When the A/B surface is actually rendered:
 *   ngOnInit() { this.flags.recordExposure('cta-copy'); }
 *
 * `recordExposure` pings `/api/feature-flags/exposures/` so the
 * analytics pipeline can correlate variants with outcomes. Fires at
 * most once per variant per session.
 */

export interface FeatureFlag {
  key: string;
  enabled: boolean;
  variant?: string;
}

const STORAGE_KEY = 'xfil_feature_flags_cache';

@Injectable({ providedIn: 'root' })
export class FeatureFlagsService {
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);

  private readonly flags = signal<Readonly<Record<string, FeatureFlag>>>(
    this.readCache(),
  );
  private readonly exposed = new Set<string>();

  /** Wire once from app bootstrap. Subsequent calls are no-ops. */
  start(): void {
    this.refresh();
  }

  /** Force a refresh — useful after the admin edits a flag. */
  refresh(): void {
    this.http
      .get<FeatureFlag[]>('/api/feature-flags/')
      .pipe(
        catchError(() => of<FeatureFlag[]>([])),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((list) => {
        if (!Array.isArray(list) || list.length === 0) return;
        const map: Record<string, FeatureFlag> = {};
        for (const f of list) map[f.key] = f;
        this.flags.set(map);
        this.writeCache(map);
      });
  }

  isEnabled(key: string): boolean {
    const hit = this.flags()[key];
    return !!hit?.enabled;
  }

  /** Returns the variant name for an A/B-keyed flag. Default 'control'
   *  when the flag is disabled or unknown. Callers compare against
   *  their own set of variant strings. */
  variantOf(key: string): string {
    const hit = this.flags()[key];
    if (!hit?.enabled) return 'control';
    return hit.variant ?? 'control';
  }

  /** Fire-and-forget "the user saw variant X" event — the backend's
   *  analytics layer joins exposures to outcomes. Idempotent within
   *  a session. */
  recordExposure(key: string): void {
    if (this.exposed.has(key)) return;
    this.exposed.add(key);
    const variant = this.variantOf(key);
    try {
      fetch('/api/feature-flags/exposures/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ key, variant }),
      }).catch(() => { /* best-effort */ });
    } catch {
      // No-op.
    }
  }

  /** Snapshot — used by the admin UI and debug overlay. */
  all(): FeatureFlag[] {
    return Object.values(this.flags());
  }

  // ── cache ──────────────────────────────────────────────────────────

  private readCache(): Record<string, FeatureFlag> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw) as Record<string, FeatureFlag>;
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  private writeCache(map: Record<string, FeatureFlag>): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    } catch {
      // No-op.
    }
  }
}
