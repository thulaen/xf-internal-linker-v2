import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of, Subject, throwError } from 'rxjs';

import { AccuracyLabCardComponent } from './accuracy-lab-card.component';
import {
  AccuracyLabFindingsResponse,
  AccuracyLabSummary,
  AccuracyLabStatus,
  AccuracyLabTools,
  DiagnosticsService,
} from '../diagnostics.service';

const checks = [
  { id: 'matlab', name: 'MATLAB', status: 'not_run' as const, message: 'Not run yet' },
  {
    id: 'numeric_precision',
    name: 'Numeric precision',
    status: 'not_run' as const,
    message: 'Not run yet',
  },
  {
    id: 'ranking_parity',
    name: 'Ranking parity',
    status: 'not_run' as const,
    message: 'Not run yet',
  },
  { id: 'schema_drift', name: 'Schema drift', status: 'not_run' as const, message: 'Not run yet' },
  { id: 'test_gaps', name: 'Test gaps', status: 'not_run' as const, message: 'Not run yet' },
  { id: 'agent_report', name: 'Agent report', status: 'not_run' as const, message: 'Not run yet' },
];

function summary(status: AccuracyLabSummary['status']): AccuracyLabSummary {
  return {
    generated_at: null,
    status,
    message:
      status === 'not_run' ? 'Accuracy Lab has not generated a local report yet.' : 'Loaded.',
    summary: {
      total_findings: 0,
      status,
      risk_counts: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
    },
    checks: checks.map((check) => ({ ...check, status })),
    sophisticated_checks: [
      {
        id: 'matlab_process_cleanup',
        name: 'MATLAB process cleanup',
        status: 'passed',
        message: 'No new MATLAB process remained after the run.',
        category: 'runtime',
        summary: 'No leftover MATLAB process.',
      },
    ],
  };
}

function tools(status: string, version: string | null = null): AccuracyLabTools {
  return {
    generated_at: null,
    tools: {
      matlab: {
        available: status !== 'missing',
        status: status as AccuracyLabStatus,
        version,
        java: null,
        desktop: null,
        path: null,
        cleanup_status: status === 'passed' ? 'clean' : 'not_checked',
        thread_policy: {
          min_cores: 4,
          max_threads: 6,
          thread_cap: 6,
          core_count: 12,
          status: status === 'passed' ? 'passed' : 'unknown',
        },
      },
    },
  };
}

function findings(risk: string | null = null): AccuracyLabFindingsResponse {
  return {
    generated_at: null,
    status: risk ? 'warning' : 'passed',
    findings: risk
      ? [
          {
            id: 'matlab-unavailable',
            title: 'MATLAB unavailable',
            risk,
            impact: 'Independent numeric checks cannot run.',
            evidence: 'matlab was not found',
            affected: 'MATLAB',
            suggested_action: 'Install MATLAB or add it to PATH.',
          },
        ]
      : [],
  };
}

describe('AccuracyLabCardComponent', () => {
  function create(
    service: Partial<DiagnosticsService>,
  ): ComponentFixture<AccuracyLabCardComponent> {
    TestBed.configureTestingModule({
      imports: [AccuracyLabCardComponent, NoopAnimationsModule],
      providers: [{ provide: DiagnosticsService, useValue: service }],
    });
    const fixture = TestBed.createComponent(AccuracyLabCardComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('shows the not-run state before any local report exists', () => {
    const fixture = create({
      getAccuracySummary: () => of(summary('not_run')),
      getAccuracyTools: () => of(tools('unknown')),
      getAccuracyFindings: () => of(findings()),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('not_run');
    expect(fixture.nativeElement.textContent).toContain('No findings in the latest report.');
  });

  it('shows a running state while the report requests are pending', () => {
    const pending = new Subject<AccuracyLabSummary>();
    const fixture = create({
      getAccuracySummary: () => pending.asObservable(),
      getAccuracyTools: () => of(tools('unknown')),
      getAccuracyFindings: () => of(findings()),
    } as Partial<DiagnosticsService>);

    const loading = fixture.nativeElement.querySelector('[data-testid="accuracy-running-state"]');

    expect(loading.textContent).toContain('Loading Accuracy Lab status');
  });

  it('shows passed state and MATLAB version when checks pass', () => {
    const fixture = create({
      getAccuracySummary: () => of(summary('passed')),
      getAccuracyTools: () => of(tools('passed', 'R2025b')),
      getAccuracyFindings: () => of(findings()),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('passed');
    expect(fixture.nativeElement.textContent).toContain('R2025b');
    expect(fixture.nativeElement.textContent).toContain('MATLAB process cleanup');
    expect(fixture.nativeElement.textContent).toContain('No leftover MATLAB process.');
    expect(fixture.nativeElement.textContent).toContain('MATLAB threads');
    expect(fixture.nativeElement.textContent).toContain('12 cores available, capped at 6');
  });

  it('shows warning findings with suggested action', () => {
    const fixture = create({
      getAccuracySummary: () => of(summary('warning')),
      getAccuracyTools: () => of(tools('passed', 'R2025b')),
      getAccuracyFindings: () => of(findings('medium')),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('MATLAB unavailable');
    expect(fixture.nativeElement.textContent).toContain('Install MATLAB or add it to PATH.');
  });

  it('shows failed state when the summary reports failure', () => {
    const fixture = create({
      getAccuracySummary: () => of(summary('failed')),
      getAccuracyTools: () => of(tools('failed')),
      getAccuracyFindings: () => of(findings('high')),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('failed');
    expect(fixture.nativeElement.textContent).toContain('high');
  });

  it('shows MATLAB unavailable state when the tool is missing', () => {
    const fixture = create({
      getAccuracySummary: () => of(summary('warning')),
      getAccuracyTools: () => of(tools('missing')),
      getAccuracyFindings: () => of(findings('medium')),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('missing');
  });

  it('shows a load failure state when the API request fails', () => {
    const fixture = create({
      getAccuracySummary: () => throwError(() => new Error('boom')),
      getAccuracyTools: () => of(tools('unknown')),
      getAccuracyFindings: () => of(findings()),
    } as Partial<DiagnosticsService>);

    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('could not be loaded');
  });

  it('starts Accuracy Lab from the Run button and refreshes the report', () => {
    const service = {
      getAccuracySummary: vi.fn(() => of(summary('warning'))),
      getAccuracyTools: vi.fn(() => of(tools('passed', 'R2025b'))),
      getAccuracyFindings: vi.fn(() => of(findings())),
      runAccuracyLab: vi.fn(() =>
        of({ status: 'warning', message: 'finished', report: null }),
      ),
    } as Partial<DiagnosticsService>;
    const fixture = create(service);
    fixture.detectChanges();

    const buttons = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const runButton = buttons.find((button) => button.textContent?.includes('Run'));
    expect(runButton).toBeTruthy();
    if (!runButton) {
      throw new Error('Run button was not rendered.');
    }
    runButton.click();
    fixture.detectChanges();

    expect(service.runAccuracyLab).toHaveBeenCalled();
    expect(service.getAccuracySummary).toHaveBeenCalledTimes(2);
  });
});
