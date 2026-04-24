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
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
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
import { Subscription, interval } from 'rxjs';

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
})
export class EmbeddingsComponent implements OnInit, OnDestroy {
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);

  loading = signal(true);
  status = signal<EmbeddingStatus | null>(null);
  settings = signal<Record<string, string>>({});
  bakeoffRows = signal<BakeoffRow[]>([]);
  gateDecisions = signal<GateDecision[]>([]);

  selectedProvider = 'local';
  fallbackProvider = 'local';
  testingProvider: string | null = null;
  busyAction: string | null = null;
  showApiKey = false;

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
  editableKeys: string[] = [
    'embedding.model',
    'embedding.api_key',
    'embedding.api_base',
    'embedding.dimensions_override',
    'embedding.monthly_budget_usd',
    'embedding.rate_limit_rpm',
  ];

  auditKeys: string[] = [
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

  // Provider switch is destructive mid-job, so keyboard arrow-key moves inside
  // the radio group update the UI selection but do not fire the POST until the
  // user explicitly confirms via Enter / Space / click.
  pendingProvider: string | null = null;

  bakeoffCols = [
    'provider',
    'mrr_at_10',
    'ndcg_at_10',
    'recall_at_10',
    'separation_score',
    'cost_usd',
    'latency_ms_p95',
    'created_at',
  ];

  decisionCols = ['created_at', 'item_kind', 'item_id', 'action', 'reason', 'score_delta'];

  private pollSub?: Subscription;

  ngOnInit(): void {
    this.refreshAll();
    // Light polling so the Overview tab reflects live provider switches.
    this.pollSub = interval(15_000).subscribe(() => this.loadStatus());
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }

  refreshAll(): void {
    this.loading.set(true);
    this.loadStatus();
    this.loadSettings();
    this.loadBakeoff();
    this.loadGateDecisions();
  }

  loadStatus(): void {
    this.http.get<EmbeddingStatus>('/api/embedding/status/').subscribe({
      next: (s) => {
        this.status.set(s);
        this.selectedProvider = s.active_provider;
        // Only seed pendingProvider the first time, or when it falls behind;
        // never overwrite a mid-edit selection the user has not applied yet.
        if (this.pendingProvider === null) {
          this.pendingProvider = s.active_provider;
        }
        this.fallbackProvider = s.fallback_provider;
        this.loading.set(false);
      },
      error: (err) => {
        console.error('embedding status error', err);
        this.loading.set(false);
      },
    });
  }

  loadSettings(): void {
    this.http.get<Record<string, string>>('/api/embedding/settings/').subscribe({
      next: (s) => this.settings.set(s),
    });
  }

  loadBakeoff(): void {
    this.http.get<BakeoffRow[]>('/api/embedding/bakeoff/').subscribe({
      next: (rows) => this.bakeoffRows.set(rows),
    });
  }

  loadGateDecisions(): void {
    this.http.get<GateDecision[]>('/api/embedding/gate-decisions/').subscribe({
      next: (rows) => this.gateDecisions.set(rows),
    });
  }

  /** Kept for template backward-compat; unused now that the radio group uses
   *  two-step apply (see applyProviderChange). */
  onProviderChange(name: string): void {
    this.pendingProvider = name;
  }

  /** Explicit keyboard-accessible apply step (WCAG 3.2.2).
   *  The radio group only updates ``pendingProvider``; the destructive
   *  provider switch does not fire until the user clicks or presses
   *  Enter/Space on the Apply button. */
  applyProviderChange(): void {
    const name = this.pendingProvider;
    if (!name) return;
    if (name === this.status()?.active_provider) return;
    this.busyAction = 'switching';
    this.http.post('/api/embedding/provider/', { name }).subscribe({
      next: () => {
        this.busyAction = null;
        this.snack.open(`Active provider: ${name}`, 'OK', { duration: 3000 });
        this.loadStatus();
      },
      error: (err) => {
        this.busyAction = null;
        this.snack.open(`Switch failed: ${err?.error?.detail || err?.message}`, 'OK', {
          duration: 5000,
        });
      },
    });
  }

  testConnection(provider: string): void {
    this.testingProvider = provider;
    this.http.post<{ ok: boolean; signature?: string; error?: string }>(
      '/api/embedding/test-connection/',
      { provider },
    ).subscribe({
      next: (res) => {
        this.testingProvider = null;
        if (res.ok) {
          this.snack.open(`${provider} connection OK (${res.signature})`, 'OK', {
            duration: 4000,
          });
        } else {
          this.snack.open(`${provider} failed: ${res.error}`, 'OK', { duration: 5000 });
        }
      },
      error: (err) => {
        this.testingProvider = null;
        this.snack.open(
          `${provider} test failed: ${err?.error?.error || err?.message}`,
          'OK',
          { duration: 5000 },
        );
      },
    });
  }

  saveSettings(): void {
    this.busyAction = 'saving';
    this.http.post('/api/embedding/settings/', this.settings()).subscribe({
      next: () => {
        this.busyAction = null;
        this.snack.open('Settings saved', 'OK', { duration: 2500 });
        this.loadStatus();
      },
      error: (err) => {
        this.busyAction = null;
        this.snack.open(`Save failed: ${err?.message}`, 'OK', { duration: 4000 });
      },
    });
  }

  runBakeoff(): void {
    this.busyAction = 'bakeoff';
    this.http.post('/api/embedding/bakeoff/run/', {}).subscribe({
      next: () => {
        this.busyAction = null;
        this.snack.open('Bake-off queued. Refresh in a few minutes.', 'OK', {
          duration: 5000,
        });
      },
      error: (err) => {
        this.busyAction = null;
        this.snack.open(`Bake-off failed to queue: ${err?.message}`, 'OK', {
          duration: 4000,
        });
      },
    });
  }

  runAudit(): void {
    this.busyAction = 'audit';
    this.http.post('/api/embedding/audit/run/', {}).subscribe({
      next: () => {
        this.busyAction = null;
        this.snack.open('Audit queued. Refresh in a few minutes.', 'OK', {
          duration: 5000,
        });
      },
      error: (err) => {
        this.busyAction = null;
        this.snack.open(`Audit failed to queue: ${err?.message}`, 'OK', {
          duration: 4000,
        });
      },
    });
  }

  setSettingValue(key: string, value: string): void {
    const updated = { ...this.settings() };
    updated[key] = value;
    this.settings.set(updated);
  }

  toggleApiKey(): void {
    this.showApiKey = !this.showApiKey;
  }
}
