import { AfterViewInit, ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, OnInit, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { catchError, finalize, of } from 'rxjs';
import * as d3 from 'd3';

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
  ],
  templateUrl: './find-bugs.component.html',
  styleUrls: ['./find-bugs.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FindBugsComponent implements OnInit, AfterViewInit {
  @ViewChild('chart')
  set chartRef(value: ElementRef<SVGElement> | undefined) {
    this.chart = value;
    this.renderChart();
  }

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

  private viewReady = false;
  private chart?: ElementRef<SVGElement>;
  private readonly service = inject(FindBugsService);
  private readonly cdr = inject(ChangeDetectorRef);

  ngOnInit(): void {
    this.refresh();
  }

  ngAfterViewInit(): void {
    this.viewReady = true;
    this.renderChart();
  }

  refresh(): void {
    this.error = '';
    this.service.summary()
      .pipe(catchError(() => {
        this.error = 'FindBugs summary could not be loaded.';
        this.cdr.markForCheck();
        return of(null);
      }))
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
    }).pipe(catchError(() => {
      this.error = 'FindBugs findings could not be loaded.';
      this.cdr.markForCheck();
      return of({ results: [] });
    })).subscribe((payload) => {
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
    const model = this.summary?.model as any;
    const reason = model?.reason || '';
    if (model?.resource_comfort?.embedding_busy) {
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
    return reason ? `Reason: ${reason}` : 'Running continuously with Rust and Haskell confirmation.';
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

  private renderChart(): void {
    if (!this.viewReady || !this.chart || !this.summary) return;
    const data = Object.entries(this.summary.severity || {}).map(([label, value]) => ({ label, value }));
    const svg = d3.select(this.chart.nativeElement);
    svg.selectAll('*').remove();
    const width = 360;
    const height = 160;
    const x = d3.scaleBand().domain(data.map((item) => item.label)).range([0, width]).padding(0.24);
    const y = d3.scaleLinear().domain([0, Math.max(1, ...data.map((item) => item.value))]).range([height, 0]);
    svg.attr('viewBox', `0 0 ${width} ${height + 28}`);
    svg.selectAll('rect')
      .data(data)
      .join('rect')
      .attr('x', (item) => x(item.label) ?? 0)
      .attr('y', (item) => y(item.value))
      .attr('width', x.bandwidth())
      .attr('height', (item) => height - y(item.value))
      .attr('rx', 4)
      .attr('class', 'severity-bar')
      .attr('fill', 'var(--color-primary)');
    svg.selectAll('text')
      .data(data)
      .join('text')
      .attr('x', (item) => (x(item.label) ?? 0) + x.bandwidth() / 2)
      .attr('y', height + 18)
      .attr('text-anchor', 'middle')
      .text((item) => item.label);
  }

  private parseDescription(finding: FindBugsFinding): Record<string, any> {
    if (!finding.description) return {};
    try {
      return JSON.parse(finding.description);
    } catch {
      return {};
    }
  }
}
