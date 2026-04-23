import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { EMPTY, of } from 'rxjs';

import { ErrorLogComponent } from './error-log.component';
import { DiagnosticsService, ErrorLogEntry } from '../diagnostics/diagnostics.service';
import { GlitchtipService } from '../core/services/glitchtip.service';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

describe('ErrorLogComponent', () => {
  const makeError = (overrides: Partial<ErrorLogEntry>): ErrorLogEntry => ({
    id: 1,
    job_type: 'pipeline',
    step: 'sync_items',
    error_message: 'A long error message that should still be visible when expanded.',
    raw_exception: 'Traceback line 1\nTraceback line 2',
    why: 'The upstream service timed out.',
    acknowledged: false,
    created_at: '2026-04-23T18:00:00Z',
    source: 'internal',
    fingerprint: 'fp-1',
    occurrence_count: 1,
    severity: 'high',
    how_to_fix: 'Retry the sync after checking the database connection.',
    node_id: 'primary',
    node_role: 'primary',
    node_hostname: 'primary-host',
    runtime_context: {},
    error_trend: [],
    related_error_ids: [],
    ...overrides,
  });

  const diagnosticsServiceStub = {
    getErrors: jasmine.createSpy('getErrors'),
    acknowledgeError: jasmine.createSpy('acknowledgeError').and.returnValue(
      of({ status: 'acknowledged' }),
    ),
  };

  const glitchtipServiceStub = {
    getRecentEvents: jasmine.createSpy('getRecentEvents'),
  };

  const visibilityGateStub = {
    whileLoggedInAndVisible: () => EMPTY,
  };

  beforeEach(() => {
    diagnosticsServiceStub.getErrors.calls.reset();
    diagnosticsServiceStub.acknowledgeError.calls.reset();
    glitchtipServiceStub.getRecentEvents.calls.reset();
  });

  it('groups multiple rows with the same fingerprint into one expansion panel', async () => {
    diagnosticsServiceStub.getErrors.and.returnValue(
      of([
        makeError({ id: 1, fingerprint: 'shared-fp', occurrence_count: 2 }),
        makeError({
          id: 2,
          fingerprint: 'shared-fp',
          occurrence_count: 3,
          created_at: '2026-04-23T17:00:00Z',
        }),
      ]),
    );
    glitchtipServiceStub.getRecentEvents.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ErrorLogComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.groupedErrors.length).toBe(1);

    const panels = fixture.nativeElement.querySelectorAll('mat-expansion-panel');
    expect(panels.length).toBe(1);

    const occurrenceBadge = fixture.nativeElement.querySelector('.occurrence-badge');
    expect(occurrenceBadge?.textContent).toContain('x5');
  });

  it('shows the full error details when a panel is expanded', async () => {
    const detailedError = makeError({
      error_message:
        'OperationalError: connection failed: connection to server at "172.18.0.8" port 5432 failed.',
      how_to_fix: 'Check the database container and retry the job.',
      raw_exception: 'Traceback (most recent call last):\nOperationalError',
    });
    diagnosticsServiceStub.getErrors.and.returnValue(of([detailedError]));
    glitchtipServiceStub.getRecentEvents.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ErrorLogComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const header = fixture.nativeElement.querySelector(
      'mat-expansion-panel-header',
    ) as HTMLElement;
    header.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain(detailedError.error_message);
    expect(text).toContain(detailedError.how_to_fix);
    expect(text).toContain(detailedError.raw_exception);
  });

  it('renders the GlitchTip outbound link on grouped GlitchTip rows', async () => {
    diagnosticsServiceStub.getErrors.and.returnValue(of([]));
    glitchtipServiceStub.getRecentEvents.and.returnValue(
      of([
        makeError({
          id: 10,
          source: 'glitchtip',
          fingerprint: 'gt-fp',
          glitchtip_issue_id: 'gt-10',
          glitchtip_url: 'http://glitchtip.local/issues/10/',
        }),
        makeError({
          id: 11,
          source: 'glitchtip',
          fingerprint: 'gt-fp',
          glitchtip_issue_id: 'gt-11',
          glitchtip_url: 'http://glitchtip.local/issues/11/',
          created_at: '2026-04-23T17:30:00Z',
        }),
      ]),
    );

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ErrorLogComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.onTabChange(1);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.componentInstance.groupedErrors.length).toBe(1);

    const header = fixture.nativeElement.querySelector(
      'mat-expansion-panel-header',
    ) as HTMLElement;
    header.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector(
      '.glitchtip-link-button',
    ) as HTMLAnchorElement;
    expect(link).toBeTruthy();
    expect(link.getAttribute('href')).toBe('http://glitchtip.local/issues/10/');
  });
});
