/**
 * Embeddings page (plan Part 8c, FR-235).
 *
 * Angular Material mat-tabs: Overview | Providers | Run Control | Bake-off | Audit.
 * Hot-switches providers (local / OpenAI / Gemini), shows live status, triggers
 * bake-off + audit, and manages all provider settings (API keys, model names,
 * budgets, gate thresholds).
 *
 * Backend API (see apps/api/embedding_views.py):
 *   GET    /api/embedding/status/
 *   GET    /api/embedding/provider/
 *   POST   /api/embedding/provider/
 *   GET    /api/embedding/settings/
 *   POST   /api/embedding/settings/
 *   POST   /api/embedding/test-connection/
 *   GET    /api/embedding/bakeoff/
 *   POST   /api/embedding/bakeoff/run/
 *   POST   /api/embedding/audit/run/
 *   GET    /api/embedding/gate-decisions/
 */

import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { interval } from 'rxjs';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

interface EmbeddingStatus {
  active_provider: string;
  fallback_provider: string;
  model_name: string;
  signature: string;
  dimension: number;
  max_tokens: number;
  hardware: {
    tier: string;
    ram_gb: number;
    cpu_cores: number;
    vram_gb: number;
    has_cuda: boolean;
    recommended_batch_size: number;
  };
  coverage: { total: number; embedded: number; pct: number };
  spend_this_month: Array<{ provider: string; cost_usd: number; tokens: number }>;
  recommended_provider: string;
}

interface BakeoffRow {
  id: number;
  job_id: string;
  provider: string;
  signature: string;
  sample_size: number;
  mrr_at_10: number;
  ndcg_at_10: number;
  recall_at_10: number;
  separation_score: number;
  cost_usd: number;
  latency_ms_p95: number;
  created_at: string;
}

interface GateDecision {
  id: number;
  item_id: number;
  item_kind: string;
  action: string;
  reason: string;
  score_delta: number;
  created_at: string;
}

@Component({
  selector: 'app-embeddings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatRadioModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatTableModule,
    MatTabsModule,
  ],
  templateUrl: './embeddings.component.html',
  styleUrls: ['./embeddings.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmbeddingsComponent implements OnInit {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  private visibilityGate = inject(VisibilityGateService);
  // Replaces the previous manual pollSub field + ngOnDestroy unsubscribe.
  // Every HTTP subscribe in this component is now piped through
  // takeUntilDestroyed so a route navigation mid-fetch correctly
  // aborts the request — the previous code leaked dozens of in-flight
  // HTTP responses on each navigation.
  private destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly status = signal<EmbeddingStatus | null>(null);
  readonly settings = signal<Record<string, string>>({});
  readonly bakeoffRows = signal<BakeoffRow[]>([]);
  readonly gateDecisions = signal<GateDecision[]>([]);

  /** Render-affecting flags. Were plain mutable fields under partial
   *  migration; now signals so OnPush picks up button-state changes
   *  (test-in-progress, save/audit/bakeoff busy markers, key visibility). */
  readonly testingProvider = signal<string | null>(null);
  readonly busyAction = signal<string | null>(null);
  readonly showApiKey = signal(false);

  // ngModel two-way binding — needs an lvalue, stays plain. The radio
  // group only writes pendingProvider; the destructive POST happens in
  // applyProviderChange below (WCAG 3.2.2 — no surprise actions on
  // arrow-key navigation through the radio group).
  pendingProvider: string | null = null;

  // Human-readable labels for every AppSetting key surfaced in the UI.
  // Raw keys like "embedding.api_key" are internal; the SR-friendly label
  // is shown via <mat-label> so assistive tech announces useful text.
  readonly labelFor: Record<string, string> = {
    'embedding.model': 'Model name',
    'embedding.api_key': 'API key',
    'embedding.api_base': 'API base URL (optional)',
    'embedding.dimensions_override': 'Dimension override (optional)',
    'embedding.monthly_budget_usd': 'Monthly budget (USD)',
    'embedding.rate_limit_rpm': 'Rate limit (requests / min)',
    'embedding.audit_resample_size': 'Audit resample size',
    'embedding.audit_norm_tolerance': 'Audit norm tolerance',
    'embedding.audit_drift_threshold': 'Audit drift threshold',
    'embedding.gate_enabled': 'Quality gate enabled',
    'embedding.gate_quality_delta_threshold': 'Gate quality-delta threshold',
    'embedding.gate_noop_cosine_threshold': 'Gate NOOP cosine threshold',
    'embedding.gate_stability_threshold': 'Gate stability threshold',
    'performance.profile_override': 'Hardware tier override',
  };

  // Which settings are editable in the Providers tab.
  readonly editableKeys: readonly string[] = [
    'embedding.model',
    'embedding.api_key',
    'embedding.api_base',
    'embedding.dimensions_override',
    'embedding.monthly_budget_usd',
    'embedding.rate_limit_rpm',
  ];

  readonly auditKeys: readonly string[] = [
    'embedding.audit_resample_size',
    'embedding.audit_norm_tolerance',
    'embedding.audit_drift_threshold',
    'embedding.gate_enabled',
    'embedding.gate_quality_delta_threshold',
    'embedding.gate_noop_cosine_threshold',
    'embedding.gate_stability_threshold',
    'performance.profile_override',
  ];

  // Numeric fields for light client-side validation + type hints.
  readonly numericKeys = new Set<string>([
    'embedding.dimensions_override',
    'embedding.monthly_budget_usd',
    'embedding.rate_limit_rpm',
    'embedding.audit_resample_size',
    'embedding.audit_norm_tolerance',
    'embedding.audit_drift_threshold',
    'embedding.gate_quality_delta_threshold',
    'embedding.gate_noop_cosine_threshold',
    'embedding.gate_stability_threshold',
  ]);

  readonly bakeoffCols: readonly string[] = [
    'provider',
    'mrr_at_10',
    'ndcg_at_10',
    'recall_at_10',
    'separation_score',
    'cost_usd',
    'latency_ms_p95',
    'created_at',
  ];

  readonly decisionCols: readonly string[] = ['created_at', 'item_kind', 'item_id', 'action', 'reason', 'score_delta'];

  ngOnInit(): void {
    this.refreshAll();
    // Light polling so the Overview tab reflects live provider switches.
    // Gated on login + visibility — paused for hidden tabs / signed-out
    // users. takeUntilDestroyed cancels the stream on route teardown,
    // replacing the previous manual pollSub unsubscribe in ngOnDestroy.
    this.visibilityGate
      .whileLoggedInAndVisible(() => interval(15_000))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadStatus());
  }

  refreshAll(): void {
    this.loading.set(true);
    this.loadStatus();
    this.loadSettings();
    this.loadBakeoff();
    this.loadGateDecisions();
  }

  loadStatus(): void {
    this.http.get<EmbeddingStatus>('/api/embedding/status/')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.status.set(s);
          // Only seed pendingProvider the first time, or when it falls behind;
          // never overwrite a mid-edit selection the user has not applied yet.
          if (this.pendingProvider === null) {
            this.pendingProvider = s.active_provider;
          }
          this.loading.set(false);
        },
        error: (err) => {
          console.error('embedding status error', err);
          this.loading.set(false);
        },
      });
  }

  loadSettings(): void {
    this.http.get<Record<string, string>>('/api/embedding/settings/')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => this.settings.set(s),
        error: (err) => console.error('embedding settings error', err),
      });
  }

  loadBakeoff(): void {
    this.http.get<BakeoffRow[]>('/api/embedding/bakeoff/')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => this.bakeoffRows.set(rows),
        error: (err) => console.error('embedding bakeoff error', err),
      });
  }

  loadGateDecisions(): void {
    this.http.get<GateDecision[]>('/api/embedding/gate-decisions/')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => this.gateDecisions.set(rows),
        error: (err) => console.error('embedding gate-decisions error', err),
      });
  }

  /** Explicit keyboard-accessible apply step (WCAG 3.2.2).
   *  The radio group only updates ``pendingProvider``; the destructive
   *  provider switch does not fire until the user clicks or presses
   *  Enter/Space on the Apply button. */
  applyProviderChange(): void {
    const name = this.pendingProvider;
    if (!name) return;
    if (name === this.status()?.active_provider) return;
    this.busyAction.set('switching');
    this.http.post('/api/embedding/provider/', { name })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyAction.set(null);
          this.snack.open(`Active provider: ${name}`, 'OK', { duration: 3000 });
          this.loadStatus();
        },
        error: (err) => {
          this.busyAction.set(null);
          this.snack.open(`Switch failed: ${err?.error?.detail || err?.message}`, 'OK', {
            duration: 5000,
          });
        },
      });
  }

  testConnection(provider: string): void {
    this.testingProvider.set(provider);
    this.http.post<{ ok: boolean; signature?: string; error?: string }>(
      '/api/embedding/test-connection/',
      { provider },
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.testingProvider.set(null);
          if (res.ok) {
            this.snack.open(`${provider} connection OK (${res.signature})`, 'OK', {
              duration: 4000,
            });
          } else {
            this.snack.open(`${provider} failed: ${res.error}`, 'OK', { duration: 5000 });
          }
        },
        error: (err) => {
          this.testingProvider.set(null);
          this.snack.open(
            `${provider} test failed: ${err?.error?.error || err?.message}`,
            'OK',
            { duration: 5000 },
          );
        },
      });
  }

  saveSettings(): void {
    this.busyAction.set('saving');
    this.http.post('/api/embedding/settings/', this.settings())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyAction.set(null);
          this.snack.open('Settings saved', 'OK', { duration: 2500 });
          this.loadStatus();
        },
        error: (err) => {
          this.busyAction.set(null);
          this.snack.open(`Save failed: ${err?.message}`, 'OK', { duration: 4000 });
        },
      });
  }

  runBakeoff(): void {
    this.busyAction.set('bakeoff');
    this.http.post('/api/embedding/bakeoff/run/', {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyAction.set(null);
          this.snack.open('Bake-off queued. Refresh in a few minutes.', 'OK', {
            duration: 5000,
          });
        },
        error: (err) => {
          this.busyAction.set(null);
          this.snack.open(`Bake-off failed to queue: ${err?.message}`, 'OK', {
            duration: 4000,
          });
        },
      });
  }

  runAudit(): void {
    this.busyAction.set('audit');
    this.http.post('/api/embedding/audit/run/', {})
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.busyAction.set(null);
          this.snack.open('Audit queued. Refresh in a few minutes.', 'OK', {
            duration: 5000,
          });
        },
        error: (err) => {
          this.busyAction.set(null);
          this.snack.open(`Audit failed to queue: ${err?.message}`, 'OK', {
            duration: 4000,
          });
        },
      });
  }

  setSettingValue(key: string, value: string): void {
    // Atomic immutable update — no separate read-then-write race on
    // rapid keystrokes and the signal observes a new reference each time.
    this.settings.update((s) => ({ ...s, [key]: value }));
  }

  toggleApiKey(): void {
    this.showApiKey.update((v) => !v);
  }
}
