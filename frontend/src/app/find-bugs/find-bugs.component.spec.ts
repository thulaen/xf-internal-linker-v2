import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { defer, of } from 'rxjs';

import { FindBugsComponent } from './find-bugs.component';
import { FindBugsService } from './find-bugs.service';

describe('FindBugsComponent', () => {
  const defaultSummary = {
    counts: { open: 2, closed: 1 },
    severity: { critical: 1, high: 1, medium: 0, low: 0 },
    artifacts: { bytes: 4096, limit_bytes: 1073741824, retention_days: 8 },
    level_a: { statement: 100, decision: 100, mcdc: 100, object_code: 100, mutation: 100 },
    model: { model: 'SmolLM2-1.7B-Instruct Q4_K_S', status: 'ok', reason: 'runner_completed' },
    model_batch: { total: 4, processed: 2, remaining: 2, state: 'processing' },
    last_run_at: '2026-05-21T16:30:00Z',
  };
  const defaultFindings = {
    results: [
      {
        id: 7,
        title: '[RUSTBUG-SEC-002] Unsafe request deserialisation',
        severity: 'critical',
        status: 'open',
        category_key: 'security',
        canonical_fingerprint: 'abc',
        affected_files: ['backend/apps/example.py'],
        occurrence_count: 3,
        description: '{"bug_pattern_id":"RUSTBUG-SEC-002","line":7,"suggested_fix":"Use JSON"}',
      },
    ],
  };
  const service = {
    summary: jasmine.createSpy('summary').and.returnValue(of(defaultSummary)),
    findings: jasmine.createSpy('findings').and.returnValue(of(defaultFindings)),
    runNow: jasmine.createSpy('runNow').and.returnValue(of({ queued: true })),
    importLatest: jasmine.createSpy('importLatest').and.returnValue(of({ imported: true })),
    pruneArtifacts: jasmine.createSpy('pruneArtifacts').and.returnValue(of({ deleted_files: 1 })),
    moveToLesson: jasmine.createSpy('moveToLesson').and.returnValue(of({ lesson_id: 9 })),
    confirmRealBug: jasmine.createSpy('confirmRealBug').and.returnValue(of({ status: 'ok' })),
    evaluateWithAgents: jasmine.createSpy('evaluateWithAgents').and.returnValue(of({ status: 'queued' })),
    duplicateCheck: jasmine.createSpy('duplicateCheck').and.returnValue(of({ status: 'ok' })),
    regressionCheck: jasmine.createSpy('regressionCheck').and.returnValue(of({ status: 'ok' })),
    generateReport: jasmine.createSpy('generateReport').and.returnValue(of({ status: 'ok' })),
    syncContext: jasmine.createSpy('syncContext').and.returnValue(of({ status: 'ok' })),
    createFixTask: jasmine.createSpy('createFixTask').and.returnValue(of({ status: 'ok' })),
    assignAgent: jasmine.createSpy('assignAgent').and.returnValue(of({ status: 'ok' })),
    approveLesson: jasmine.createSpy('approveLesson').and.returnValue(of({ status: 'ok' })),
  };

  beforeEach(() => {
    service.summary.calls.reset();
    service.findings.calls.reset();
    service.summary.and.returnValue(of(defaultSummary));
    service.findings.and.returnValue(of(defaultFindings));
    TestBed.configureTestingModule({
      imports: [FindBugsComponent, NoopAnimationsModule],
      providers: [{ provide: FindBugsService, useValue: service }],
    });
  });

  it('renders D3-backed summary, deduped findings, and action buttons', fakeAsync(() => {
    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('FindBugs');
    expect(fixture.nativeElement.textContent).toContain('RUSTBUG-SEC-002');
    expect(fixture.nativeElement.textContent).toContain('SmolLM2-1.7B-Instruct Q4_K_S');
    expect(fixture.nativeElement.textContent).toContain('Model ready');
    expect(fixture.nativeElement.textContent).toContain('processing: 2/4 processed');
    expect(fixture.nativeElement.textContent).toContain('Level A100%');
    expect(fixture.nativeElement.querySelector('.summary-card .summary-content')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.summary-card .chart-panel')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.findings-card .findings-toolbar')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('section.findbugs-page > .filter-card')).toBeFalsy();
    expect(fixture.nativeElement.querySelector('svg.findbugs-chart')).toBeTruthy();
    expect(fixture.nativeElement.querySelectorAll('svg.findbugs-chart rect.severity-bar').length).toBe(4);

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    buttons.find((button) => button.textContent?.includes('Run now'))?.click();
    buttons.find((button) => button.textContent?.includes('Import latest'))?.click();
    buttons.find((button) => button.textContent?.includes('Prune artifacts'))?.click();
    buttons.find((button) => button.textContent?.includes('Sync context'))?.click();
    buttons.find((button) => button.textContent?.includes('Generate report'))?.click();

    expect(service.runNow).toHaveBeenCalled();
    expect(service.importLatest).toHaveBeenCalled();
    expect(service.pruneArtifacts).toHaveBeenCalled();
    expect(service.syncContext).toHaveBeenCalled();
    expect(service.generateReport).toHaveBeenCalled();
  }));

  it('shows summary and findings after asynchronous backend replies', fakeAsync(() => {
    service.summary.and.returnValue(defer(() => Promise.resolve({
      counts: { open: 4, closed: 2 },
      severity: { critical: 2, high: 1, medium: 1, low: 0 },
      artifacts: { bytes: 1024, limit_bytes: 2048, retention_days: 8 },
      level_a: { statement: 100, decision: 100, mcdc: 100, object_code: 100, mutation: 100 },
      model: { model: 'SmolLM2-1.7B-Instruct Q4_K_S', status: 'ok', reason: 'runner_completed' },
      last_run_at: '2026-05-21T21:30:00Z',
    })));
    service.findings.and.returnValue(defer(() => Promise.resolve({
      results: [
        {
          id: 8,
          title: '[RUSTBUG-PERF-001] Repeated query in loop',
          severity: 'high',
          status: 'open',
          canonical_fingerprint: 'async-finding',
          affected_files: ['backend/apps/slow.py'],
          description: '{"bug_pattern_id":"RUSTBUG-PERF-001","line":12}',
        },
      ],
    })));

    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.autoDetectChanges();
    tick();

    expect(fixture.nativeElement.textContent).toContain('RUSTBUG-PERF-001');
    expect(fixture.nativeElement.textContent).toContain('Model ready');
    expect(fixture.nativeElement.textContent).toContain('50%');
  }));

  it('dedupes repeated findings by canonical fingerprint before rendering', fakeAsync(() => {
    service.findings.and.returnValue(of({
      results: [
        {
          ...defaultFindings.results[0],
          id: 7,
          canonical_fingerprint: 'same-fingerprint',
          occurrence_count: 1,
        },
        {
          ...defaultFindings.results[0],
          id: 8,
          canonical_fingerprint: 'same-fingerprint',
          occurrence_count: 4,
        },
      ],
    }));

    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('tr.finding-row');
    expect(rows.length).toBe(1);
    expect(fixture.componentInstance.findings[0].id).toBe(8);
    expect(fixture.componentInstance.findings[0].occurrence_count).toBe(4);
  }));

  it('groups repeated pattern and file findings into one operator row', fakeAsync(() => {
    service.findings.and.returnValue(of({
      results: [
        {
          ...defaultFindings.results[0],
          id: 7,
          canonical_fingerprint: 'same-file-line-7',
          occurrence_count: 1,
        },
        {
          ...defaultFindings.results[0],
          id: 8,
          canonical_fingerprint: 'same-file-line-21',
          occurrence_count: 2,
          description: '{"bug_pattern_id":"RUSTBUG-SEC-002","line":21,"suggested_fix":"Use JSON"}',
        },
      ],
    }));

    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('tr.finding-row');
    expect(rows.length).toBe(1);
    expect(fixture.componentInstance.findings[0].id).toBe(8);
    expect(fixture.componentInstance.findings[0].occurrence_count).toBe(3);
    const expandButton = fixture.nativeElement.querySelector('button[aria-label="Expand bug details"]') as HTMLButtonElement;
    expandButton.click();
    fixture.detectChanges();
    tick();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('3 grouped');
    expect(fixture.nativeElement.textContent).toContain('Problem details');
    expect(fixture.nativeElement.textContent).toContain('Copy for agents');
    expect(fixture.nativeElement.textContent).toContain('Use JSON');
  }));

  it('shows model notes inside expanded bug rows', fakeAsync(() => {
    service.findings.and.returnValue(of({
      results: [
        {
          ...defaultFindings.results[0],
          description: JSON.stringify({
            bug_pattern_id: 'RUSTBUG-SEC-002',
            line: 7,
            suggested_fix: 'Use JSON',
            model_batch: {
              notes: {
                category: 'security',
                affected: 'Request parser',
                what_to_do: 'Replace pickle with schema-validated JSON.',
              },
            },
          }),
        },
      ],
    }));

    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const expandButton = fixture.nativeElement.querySelector('button[aria-label="Expand bug details"]') as HTMLButtonElement;
    expandButton.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Model notes');
    expect(fixture.nativeElement.textContent).toContain('Category: security');
    expect(fixture.nativeElement.textContent).toContain('Request parser');
    expect(fixture.nativeElement.textContent).toContain('schema-validated JSON');
  }));

  it('wires selected issue actions to backend calls', fakeAsync(() => {
    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const click = (label: string) => {
      const menuButton = fixture.nativeElement.querySelector('button[aria-label="Issue actions"]') as HTMLButtonElement;
      menuButton.click();
      fixture.detectChanges();
      tick();
      fixture.detectChanges();
      const button = document.body.querySelector(`button[aria-label="${label}"]`) as HTMLButtonElement;
      expect(button).withContext(label).toBeTruthy();
      button.click();
      fixture.detectChanges();
      tick();
    };

    click('Evaluate with agents');
    click('Re-evaluate issue');
    click('Confirm real bug');
    click('Create fix task');
    click('Assign to agent');
    click('Run duplicate check');
    click('Run regression check');
    click('Approve lesson');

    expect(service.evaluateWithAgents).toHaveBeenCalledWith([7], 'codex');
    expect(service.confirmRealBug).toHaveBeenCalledWith(7);
    expect(service.createFixTask).toHaveBeenCalledWith(7);
    expect(service.assignAgent).toHaveBeenCalledWith(7, 'codex');
    expect(service.duplicateCheck).toHaveBeenCalledWith(7);
    expect(service.regressionCheck).toHaveBeenCalledWith(7);
    expect(service.approveLesson).toHaveBeenCalledWith(7);
  }));

  it('moves a selected non-bug to learned lessons', fakeAsync(() => {
    const fixture = TestBed.createComponent(FindBugsComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const menuButton = fixture.nativeElement.querySelector('button[aria-label="Issue actions"]') as HTMLButtonElement;
    menuButton.click();
    fixture.detectChanges();
    tick();
    fixture.detectChanges();
    const falsePositive = document.body.querySelector('button[aria-label="Mark false positive"]') as HTMLButtonElement;
    falsePositive.click();

    expect(service.moveToLesson).toHaveBeenCalledWith(
      7,
      'false_positive',
      jasmine.stringMatching('Trap:'),
    );
  }));
});
