import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { EMPTY, of, throwError, Subject } from 'rxjs';

import { ErrorLogComponent } from './error-log.component';
import { DiagnosticsService, ErrorLogEntry } from '../diagnostics/diagnostics.service';
import { AutoIssuesService } from '../core/services/auto-issues.service';
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

  const autoIssuesServiceStub = {
    list: jasmine.createSpy('list').and.returnValue(of({ count: 0, next: null, previous: null, results: [] })),
    resync: jasmine.createSpy('resync').and.returnValue(of({})),
    flushCache: jasmine.createSpy('flushCache').and.returnValue(of({})),
  };

  const visibilityGateStub = {
    whileLoggedInAndVisible: () => EMPTY,
  };

  beforeEach(() => {
    diagnosticsServiceStub.getErrors.calls.reset();
    diagnosticsServiceStub.acknowledgeError.calls.reset();
    glitchtipServiceStub.getRecentEvents.calls.reset();
    autoIssuesServiceStub.list.calls.reset();
    autoIssuesServiceStub.resync.calls.reset();
    autoIssuesServiceStub.flushCache.calls.reset();
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
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
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
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
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

  it('Auto-Issues tab loads ONLY open status — never fetches resolved (2026-05-09 noise rule)', async () => {
    diagnosticsServiceStub.getErrors.and.returnValue(of([]));
    glitchtipServiceStub.getRecentEvents.and.returnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ErrorLogComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    fixture.componentInstance.loadAutoIssues();
    fixture.detectChanges();
    await fixture.whenStable();

    // Exactly one call, with status=open. Resolved must NOT be requested.
    expect(autoIssuesServiceStub.list.calls.count()).toBe(1);
    expect(autoIssuesServiceStub.list.calls.argsFor(0)).toEqual([{ status: 'open' }]);
    const everyCall = autoIssuesServiceStub.list.calls.allArgs();
    const fetchedResolved = everyCall.some((args) => args[0]?.status === 'resolved');
    expect(fetchedResolved).toBe(false);
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
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
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

  // Kills the surviving Stryker mutants on severityLabel()/sourceLabel()
  // (AutoIssues #19072 toLowerCase, #19074 ternary-condition-true, plus the
  // #19071 arithmetic, #19073 block-empty, #19075 equality mutants): these
  // assert the exact rendered label text, which the prior GlitchTip
  // href-only test never read. Each block builds its own component because
  // the surrounding `it()` blocks each scope `fixture` locally — there is no
  // shared module-level fixture to borrow.
  const buildComponent = async (): Promise<ErrorLogComponent> => {
    diagnosticsServiceStub.getErrors.and.returnValue(of([]));
    glitchtipServiceStub.getRecentEvents.and.returnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();
    return TestBed.createComponent(ErrorLogComponent).componentInstance;
  };

  it('severityLabel capitalises the first letter exactly', async () => {
    const c = await buildComponent();
    expect(c.severityLabel(makeError({ severity: 'high' }))).toBe('High');
    expect(c.severityLabel(makeError({ severity: 'medium' }))).toBe('Medium');
    expect(c.severityLabel(makeError({ severity: undefined }))).toBe('Medium');
  });

  it('sourceLabel maps both branches to exact text', async () => {
    const c = await buildComponent();
    expect(c.sourceLabel(makeError({ source: 'glitchtip' }))).toBe('GlitchTip');
    expect(c.sourceLabel(makeError({ source: 'internal' }))).toBe('Internal');
  });

  it('jobTypeLabel maps known types and falls back to original', async () => {
    const c = await buildComponent();
    expect(c.jobTypeLabel('import')).toBe('Import');
    expect(c.jobTypeLabel('embed')).toBe('Embed');
    expect(c.jobTypeLabel('pipeline')).toBe('Pipeline');
    expect(c.jobTypeLabel('sync')).toBe('Sync');
    expect(c.jobTypeLabel('auto_tune_weights')).toBe('Auto-Tune');
    expect(c.jobTypeLabel('unknown_job_type')).toBe('unknown_job_type');
  });

  it('previewMessage handles short, missing, and long messages correctly', async () => {
    const c = await buildComponent();
    expect(c.previewMessage(makeError({ error_message: undefined as any }))).toBe('');
    expect(c.previewMessage(makeError({ error_message: '  short  ' }))).toBe('short');
    
    const longMsg = 'A'.repeat(150);
    const result = c.previewMessage(makeError({ error_message: longMsg }));
    expect(result).toBe('A'.repeat(137) + '...');
    expect(result.length).toBe(140);

    const customResult = c.previewMessage(makeError({ error_message: longMsg }), 10);
    expect(customResult).toBe('A'.repeat(7) + '...');
    expect(customResult.length).toBe(10);
  });

  it('acknowledgeError reloads errors and glitchtip events when source is glitchtip', async () => {
    const c = await buildComponent();
    spyOn(c, 'loadErrors');
    spyOn(c, 'loadGlitchtipEvents');
    diagnosticsServiceStub.acknowledgeError.and.returnValue(of({ status: 'acknowledged' }));
    c.acknowledgeError(makeError({ source: 'glitchtip' }));
    expect(c.loadErrors).toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).toHaveBeenCalled();
  });

  it('acknowledgeError does not reload glitchtip events if source is internal', async () => {
    const c = await buildComponent();
    spyOn(c, 'loadErrors');
    spyOn(c, 'loadGlitchtipEvents');
    diagnosticsServiceStub.acknowledgeError.and.returnValue(of({ status: 'acknowledged' }));
    c.acknowledgeError(makeError({ source: 'internal' }));
    expect(c.loadErrors).toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).not.toHaveBeenCalled();
  });

  it('acknowledgeError reloads errors even if acknowledgeError fails', async () => {
    const c = await buildComponent();
    spyOn(c, 'loadErrors');
    diagnosticsServiceStub.acknowledgeError.and.returnValue(throwError(() => new Error('fail')));
    c.acknowledgeError(makeError({ source: 'internal' }));
    expect(c.loadErrors).toHaveBeenCalled();
  });

  it('resync populates resyncStatus and resyncBusy on success and failure', async () => {
    const c = await buildComponent();

    autoIssuesServiceStub.resync.and.returnValue(of({ open_count: 5 }));
    c.resync();
    expect(c.resyncBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Synced — 5 open issues now');

    autoIssuesServiceStub.resync.and.returnValue(throwError(() => ({ statusText: 'Bad Gateway' })));
    c.resync();
    expect(c.resyncBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Resync failed: Bad Gateway');

    autoIssuesServiceStub.resync.and.returnValue(throwError(() => ({})));
    c.resync();
    expect(c.resyncBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Resync failed: unknown');
  });

  it('flushCache populates resyncStatus and flushBusy on success and failure', async () => {
    const c = await buildComponent();
    const markForCheckSpy = spyOn((c as any).cdr, 'markForCheck');

    autoIssuesServiceStub.flushCache.and.returnValue(of({ flushed_rows: 10 }));
    c.flushCache();
    expect(c.flushBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Flushed 10 stale rows');
    expect(markForCheckSpy).toHaveBeenCalled();
    markForCheckSpy.calls.reset();

    autoIssuesServiceStub.flushCache.and.returnValue(throwError(() => ({ statusText: 'Server Error' })));
    c.flushCache();
    expect(c.flushBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Flush failed: Server Error');
    expect(markForCheckSpy).toHaveBeenCalled();
    markForCheckSpy.calls.reset();

    autoIssuesServiceStub.flushCache.and.returnValue(throwError(() => ({})));
    c.flushCache();
    expect(c.flushBusy).toBeFalse();
    expect(c.resyncStatus).toBe('Flush failed: unknown');
    expect(markForCheckSpy).toHaveBeenCalled();
  });

  it('flushCache subscription is cleaned up when component is destroyed', async () => {
    diagnosticsServiceStub.getErrors.and.returnValue(of([]));
    glitchtipServiceStub.getRecentEvents.and.returnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const flushSubject = new Subject<any>();
    autoIssuesServiceStub.flushCache.and.returnValue(flushSubject.asObservable());

    const fixture = TestBed.createComponent(ErrorLogComponent);
    const c = fixture.componentInstance;
    c.flushCache();

    fixture.destroy();

    flushSubject.next({ flushed_rows: 5 });
    
    // resyncStatus should remain null since the subscription was destroyed
    expect(c.resyncStatus).toBeNull();
  });

  it('filteredErrors returns glitchtipEvents when on glitchtip tab', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 1; // GLITCHTIP_TAB_INDEX
    c.glitchtipEvents = [makeError({ source: 'glitchtip' })];
    expect(c.filteredErrors).toBe(c.glitchtipEvents);
  });

  it('filteredErrors filters out glitchtip events when on internal tab', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0; // internal tab
    c.errors = [
      makeError({ id: 1, source: 'internal', acknowledged: false }),
      makeError({ id: 2, source: 'glitchtip', acknowledged: false }),
    ];
    c.filterJobType = '';
    c.filterAcknowledged = 'unreviewed';
    const result = c.filteredErrors;
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(1);
  });

  it('filteredErrors returns all errors when on all tab', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 2; // ALL_TAB_INDEX
    c.errors = [
      makeError({ id: 1, source: 'internal', acknowledged: false }),
      makeError({ id: 2, source: 'glitchtip', acknowledged: false }),
    ];
    c.filterJobType = '';
    c.filterAcknowledged = 'unreviewed';
    const result = c.filteredErrors;
    expect(result.length).toBe(2);
  });
});
