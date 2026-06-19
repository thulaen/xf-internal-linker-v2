import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { forkJoin } from 'rxjs';
import {
  AccuracyLabCheck,
  AccuracyLabFinding,
  AccuracyLabFindingsResponse,
  AccuracyLabStatus,
  AccuracyLabSummary,
  AccuracyLabTools,
  DiagnosticsService,
} from '../diagnostics.service';

interface AccuracyLabViewModel {
  summary: AccuracyLabSummary;
  tools: AccuracyLabTools;
  findings: AccuracyLabFinding[];
}

interface AccuracyStatusCard {
  id: string;
  label: string;
  status: string;
  detail: string;
}

type AccuracyLabThreadPolicy = NonNullable<
  NonNullable<AccuracyLabTools['tools']['matlab']>['thread_policy']
>;

@Component({
  selector: 'app-accuracy-lab-card',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './accuracy-lab-card.component.html',
  styleUrls: ['./accuracy-lab-card.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AccuracyLabCardComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);
  private destroyRef = inject(DestroyRef);

  readonly reportUrl = '/api/system/status/accuracy/report/';
  readonly loading = signal(true);
  readonly running = signal(false);
  readonly loadFailed = signal(false);
  readonly runError = signal<string | null>(null);
  readonly vm = signal<AccuracyLabViewModel | null>(null);

  readonly statusCards = computed<AccuracyStatusCard[]>(() => {
    const view = this.vm();
    if (!view) return [];
    const matlab = view.tools.tools.matlab;
    const byId = new Map(view.summary.checks.map((check) => [check.id, check]));
    return [
      this.card('matlab', 'MATLAB', matlab?.status ?? 'unknown', matlab?.version ?? 'Not found'),
      this.cardFromCheck(byId, 'numeric_precision', 'Numeric precision'),
      this.cardFromCheck(byId, 'ranking_parity', 'Ranking parity'),
      this.cardFromCheck(byId, 'schema_drift', 'Schema drift'),
      this.cardFromCheck(byId, 'test_gaps', 'Test gaps'),
      this.cardFromCheck(byId, 'agent_report', 'Agent report'),
      this.card(
        'matlab_cleanup',
        'MATLAB cleanup',
        matlab?.cleanup_status === 'clean' ? 'passed' : 'unknown',
        matlab?.cleanup_status ?? 'Not checked',
      ),
      this.card(
        'matlab_threads',
        'MATLAB threads',
        this.threadPolicyStatus(matlab?.thread_policy),
        this.threadPolicyDetail(matlab?.thread_policy),
      ),
    ];
  });
  readonly advancedChecks = computed<AccuracyLabCheck[]>(
    () => this.vm()?.summary.sophisticated_checks ?? [],
  );

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadFailed.set(false);
    forkJoin({
      summary: this.diagnosticsService.getAccuracySummary(),
      tools: this.diagnosticsService.getAccuracyTools(),
      findings: this.diagnosticsService.getAccuracyFindings(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.vm.set({
            summary: data.summary,
            tools: data.tools,
            findings: this.findingsFrom(data.findings),
          });
          this.loading.set(false);
        },
        error: () => {
          this.vm.set(null);
          this.loadFailed.set(true);
          this.loading.set(false);
        },
      });
  }

  run(): void {
    this.running.set(true);
    this.runError.set(null);
    this.diagnosticsService
      .runAccuracyLab()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.running.set(false);
          this.load();
        },
        error: (err) => {
          this.running.set(false);
          this.runError.set(err?.error?.message ?? 'Accuracy Lab could not run.');
          this.load();
        },
      });
  }

  statusClass(status: string): string {
    return `accuracy-status accuracy-status--${status.replace('_', '-')}`;
  }

  private findingsFrom(response: AccuracyLabFindingsResponse): AccuracyLabFinding[] {
    return response.findings ?? [];
  }

  private card(
    id: string,
    label: string,
    status: AccuracyLabStatus | string,
    detail: string,
  ): AccuracyStatusCard {
    return { id, label, status, detail };
  }

  private cardFromCheck(
    checks: Map<string, AccuracyLabCheck>,
    id: string,
    label: string,
  ): AccuracyStatusCard {
    const check = checks.get(id);
    return this.card(id, label, check?.status ?? 'not_run', check?.message ?? 'Not run yet');
  }

  private threadPolicyDetail(policy: AccuracyLabThreadPolicy | undefined): string {
    if (!policy) return 'Not checked';
    return `${policy.core_count ?? '?'} cores available, capped at ${policy.thread_cap ?? '?'}`;
  }

  private threadPolicyStatus(policy: AccuracyLabThreadPolicy | undefined): string {
    if (!policy) return 'unknown';
    if (policy.status === 'passed') return 'passed';
    if (policy.status === 'too_few_cores' || policy.status === 'too_many_threads') {
      return 'failed';
    }
    return 'unknown';
  }
}
