import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { catchError, finalize, of } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import type { EChartsOption } from 'echarts';

import { EchartsDirective } from '../shared/charts/echarts.directive';
import { PeHelperDirective } from '../shared/directives/pe-helper.directive';
import { gscChartBase, token, withAlpha } from '../shared/charts/echarts-theme';

import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';

import { FindBugsFinding, FindBugsService, FindBugsSummary } from './find-bugs.service';

@Component({
  selector: 'app-find-bugs',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatMenuModule,
    MatProgressBarModule,
    MatSelectModule,
    MatTableModule,
    MatTooltipModule,
    EchartsDirective,
    PeHelperDirective,
  ],
  templateUrl: './find-bugs.component.html',
  styleUrls: ['./find-bugs.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FindBugsComponent implements OnInit {
  /**
   * Severity bar chart option. `null` until the summary loads (or when the
   * summary carries no severity counts) so the template shows a truthful
   * empty state, never a blank chart implying "no bugs".
   */
  readonly severityChart = signal<EChartsOption | null>(null);

  readonly displayedColumns = ['expand', 'pattern', 'severity', 'status', 'file', 'confirmedBy', 'actions'];
  readonly severities = ['', 'critical', 'high', 'medium', 'low'];
  readonly statuses = ['', 'open', 'picked', 'fixing', 'resolved', 'deferred'];

  summary: FindBugsSummary | null = null;
  findings: FindBugsFinding[] = [];
  search = '';
  severity = '';
  status = 'open';
  busy = false;
  error = '';
  expandedFindingId: number | null = null;

  private readonly service = inject(FindBugsService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.error = '';
    this.service.summary()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        catchError(() => {
          this.error = 'FindBugs summary could not be loaded.';
          this.cdr.markForCheck();
          return of(null);
        })
      )
      .subscribe((summary) => {
        this.summary = summary;
        this.renderChart();
        this.cdr.markForCheck();
      });
    this.loadFindings();
  }

  loadFindings(): void {
    this.service.findings({
      search: this.search,
      severity: this.severity,
      status: this.status,
    }).pipe(
      takeUntilDestroyed(this.destroyRef),
      catchError(() => {
        this.error = 'FindBugs findings could not be loaded.';
        this.cdr.markForCheck();
        return of({ results: [] });
      })
    ).subscribe((payload) => {
      this.findings = this.dedupeFindings(payload.results);
      this.cdr.markForCheck();
    });
  }

  runNow(): void {
    this.runAction(() => this.service.runNow());
  }

  importLatest(): void {
    this.runAction(() => this.service.importLatest());
  }

  pruneArtifacts(): void {
    this.runAction(() => this.service.pruneArtifacts());
  }

  syncContext(): void {
    this.runAction(() => this.service.syncContext());
  }

  generateReport(): void {
    this.runAction(() => this.service.generateReport());
  }

  evaluateWithAgents(finding: FindBugsFinding): void {
    this.runAction(() => this.service.evaluateWithAgents([finding.id], 'codex'));
  }

  reEvaluateIssue(finding: FindBugsFinding): void {
    this.evaluateWithAgents(finding);
  }

  confirmRealBug(finding: FindBugsFinding): void {
    this.runAction(() => this.service.confirmRealBug(finding.id));
  }

  createFixTask(finding: FindBugsFinding): void {
    this.runAction(() => this.service.createFixTask(finding.id));
  }

  assignToAgent(finding: FindBugsFinding): void {
    this.runAction(() => this.service.assignAgent(finding.id, 'codex'));
  }

  runDuplicateCheck(finding: FindBugsFinding): void {
    this.runAction(() => this.service.duplicateCheck(finding.id));
  }

  runRegressionCheck(finding: FindBugsFinding): void {
    this.runAction(() => this.service.regressionCheck(finding.id));
  }

  approveLesson(finding: FindBugsFinding): void {
    this.runAction(() => this.service.approveLesson(finding.id));
  }

  markFalsePositive(finding: FindBugsFinding): void {
    this.moveToLesson(finding, 'false_positive');
  }

  markFalseNegative(finding: FindBugsFinding): void {
    this.moveToLesson(finding, 'false_negative');
  }

  artifactPercent(): number {
    const artifacts = this.summary?.artifacts;
    if (!artifacts?.limit_bytes) return 0;
    return Math.min(100, Math.round((artifacts.bytes / artifacts.limit_bytes) * 100));
  }

  levelAStatement(): number {
    return this.summary?.level_a?.['statement'] ?? 0;
  }

  modelLabel(): string {
    const status = this.summary?.model?.status || 'unknown';
    if (status === 'ok' || status === 'ready') return 'Model ready';
    if (status === 'missing' || status === 'unavailable') return 'Model unavailable';
    if (status === 'failed') return 'Model needs attention';
    return 'Model status unknown';
  }

  modelName(): string {
    return this.summary?.model?.model || 'SmolLM2-1.7B-Instruct Q4_K_S';
  }

  modelDetail(): string {
    const model = this.summary?.model;
    const reason = model?.reason || '';
    if ((model as Record<string, unknown>)?.['resource_comfort'] && ((model as Record<string, unknown>)['resource_comfort'] as Record<string, unknown>)?.['embedding_busy']) {
      return 'Running beside embeddings; VictoriaMetrics will file a tuning issue if pressure is too high.';
    }
    if (reason === 'embeddings_busy') {
      return 'Running beside embeddings; VictoriaMetrics will watch resource pressure.';
    }
    if (reason === 'model_missing') {
      return 'SmolLM2 is not installed in the configured model folder.';
    }
    if (reason === 'runner_disabled') {
      return 'The model runner is disabled by policy for this environment.';
    }
    if (reason === 'runner_completed') {
      return 'Running continuously with bounded time and output limits.';
    }
    return reason ? `Reason: ${reason}` : 'Running continuously with Rust confirmation.';
  }

  batchProgressValue(): number {
    const batch = this.summary?.model_batch;
    if (!batch?.total) return 0;
    return Math.round((batch.processed / batch.total) * 100);
  }

  batchProgressLabel(): string {
    const batch = this.summary?.model_batch;
    if (!batch) return 'Model batch sleeping';
    return `${batch.state}: ${batch.processed}/${batch.total} processed`;
  }

  pattern(finding: FindBugsFinding): string {
    return finding.bug_pattern_id || this.parseDescription(finding)['bug_pattern_id'] || finding.title;
  }

  fileLine(finding: FindBugsFinding): string {
    const file = finding.file || finding.affected_files?.[0] || '';
    const line = finding.line || this.parseDescription(finding)['line'];
    return line ? `${file}:${line}` : file;
  }

  groupedCount(finding: FindBugsFinding): number {
    return Math.max(1, finding.occurrence_count ?? finding.grouped_findings?.length ?? 1);
  }

  toggleExpanded(finding: FindBugsFinding): void {
    this.expandedFindingId = this.expandedFindingId === finding.id ? null : finding.id;
  }

  isExpanded(finding: FindBugsFinding): boolean {
    return this.expandedFindingId === finding.id;
  }

  agentProblemText(finding: FindBugsFinding): string {
    const detail = this.parseDescription(finding);
    return [
      `Pattern: ${this.pattern(finding)}`,
      `Severity: ${finding.severity}`,
      `Status: ${finding.status}`,
      `File: ${this.fileLine(finding)}`,
      `Confirmed by: ${finding.confirmed_by || 'rust'}`,
      `Problem: ${detail['message'] || detail['description'] || finding.title}`,
      `Suggested fix: ${detail['suggested_fix'] || 'Review the detector evidence and apply the narrowest safe fix.'}`,
      `Model notes: ${this.modelNotesText(finding)}`,
      `Grouped findings: ${this.groupedCount(finding)}`,
    ].join('\n');
  }

  modelNotesText(finding: FindBugsFinding): string {
    const notes = this.parseDescription(finding)['model_batch']?.['notes'];
    if (!notes || Object.keys(notes).length === 0) return 'No model batch notes yet.';
    return [
      notes['category'] ? `Category: ${notes['category']}` : '',
      notes['affected'] ? `Affected: ${notes['affected']}` : '',
      notes['what_to_do'] ? `What to do: ${notes['what_to_do']}` : '',
    ].filter(Boolean).join(' ');
  }

  copyForAgents(finding: FindBugsFinding): void {
    void navigator.clipboard?.writeText(this.agentProblemText(finding));
  }

  openInErrorLog(finding: FindBugsFinding): void {
    window.open(`/error-log?source=rust_defect&id=${finding.id}`, '_blank', 'noopener,noreferrer');
  }

  private runAction(action: () => ReturnType<FindBugsService['runNow']>): void {
    this.busy = true;
    this.cdr.markForCheck();
    action().pipe(finalize(() => {
      this.busy = false;
      this.refresh();
      this.cdr.markForCheck();
    })).subscribe({ error: () => { this.error = 'FindBugs action failed.'; } });
  }

  private dedupeFindings(findings: FindBugsFinding[]): FindBugsFinding[] {
    const exact = new Map<string, FindBugsFinding>();
    for (const finding of findings) {
      const key = finding.canonical_fingerprint || `${this.pattern(finding)}:${this.fileLine(finding)}`;
      const previous = exact.get(key);
      if (!previous || this.rankFinding(finding) > this.rankFinding(previous)) {
        exact.set(key, finding);
      }
    }

    const groups = new Map<string, FindBugsFinding[]>();
    for (const finding of exact.values()) {
      const key = this.dedupeKey(finding);
      groups.set(key, [...(groups.get(key) ?? []), finding]);
    }
    return Array.from(groups.values()).map((group) => this.groupFindings(group));
  }

  private dedupeKey(finding: FindBugsFinding): string {
    const file = finding.file || finding.affected_files?.[0] || '';
    return `${this.pattern(finding)}:${file}`;
  }

  private groupFindings(group: FindBugsFinding[]): FindBugsFinding {
    const sorted = [...group].sort((a, b) => this.rankFinding(b) - this.rankFinding(a));
    const winner = { ...sorted[0] };
    winner.grouped_findings = sorted;
    winner.occurrence_count = sorted.reduce(
      (total, finding) => total + Math.max(1, finding.occurrence_count ?? 1),
      0,
    );
    return winner;
  }

  private rankFinding(finding: FindBugsFinding): number {
    return (finding.occurrence_count ?? 0) * 1_000_000 + finding.id;
  }

  private moveToLesson(
    finding: FindBugsFinding,
    classification: 'false_positive' | 'false_negative',
  ): void {
    const lesson = [
      `Trap: ${this.pattern(finding)} was classified as ${classification.replace('_', ' ')}.`,
      'Fix shape: keep this decision as a compressed FindBugs lesson for future agent review.',
    ].join(' ');
    this.runAction(() => this.service.moveToLesson(finding.id, classification, lesson));
  }

  /**
   * Build the severity bar chart from the summary's severity counts. Sets
   * `severityChart` to `null` when there is no data so the template renders a
   * truthful empty state instead of an empty chart. Pure transform of the
   * summary — no DOM access, so it is safe to call before the view is ready.
   */
  private renderChart(): void {
    const entries = Object.entries(this.summary?.severity ?? {});
    if (entries.length === 0) {
      this.severityChart.set(null);
      return;
    }
    this.severityChart.set(buildSeverityChart(entries));
  }

  private parseDescription(finding: FindBugsFinding): Record<string, unknown> {
    if (!finding.description) return {};
    try {
      return JSON.parse(finding.description) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
}

/**
 * Build the ECharts bar option for the severity spread. Top-level pure
 * function — easy to test, no component state captured. Bars use the tokened
 * GSC blue (`var(--color-primary)`) so the chart stays inside the design
 * system rather than a hardcoded hex.
 */
function buildSeverityChart(entries: [string, number][]): EChartsOption {
  const base = gscChartBase();
  const muted = token('--color-text-muted');
  return {
    ...base,
    tooltip: { ...(base['tooltip'] as object), trigger: 'axis' },
    legend: { show: false },
    grid: { left: 8, right: 16, top: 16, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: entries.map(([label]) => label),
      axisLabel: { color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: token('--color-border') } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: withAlpha(muted, 0.1) } },
    },
    series: [
      {
        type: 'bar',
        data: entries.map(([, value]) => value),
        itemStyle: { color: token('--color-primary'), borderRadius: [4, 4, 0, 0] },
        barMaxWidth: 48,
      },
    ],
  };
}
