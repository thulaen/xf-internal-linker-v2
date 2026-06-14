import { provideHttpClient, withXhr } from '@angular/common/http';
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
    getErrors: vi.fn(),
    acknowledgeError: vi.fn().mockReturnValue(of({ status: 'acknowledged' })),
  };

  const glitchtipServiceStub = {
    getRecentEvents: vi.fn(),
  };

  const autoIssuesServiceStub = {
    list: vi.fn().mockReturnValue(of({ count: 0, next: null, previous: null, results: [] })),
    resync: vi.fn().mockReturnValue(of({})),
    flushCache: vi.fn().mockReturnValue(of({})),
  };

  const visibilityGateStub = {
    whileLoggedInAndVisible: () => EMPTY,
  };

  beforeEach(() => {
    diagnosticsServiceStub.getErrors.mockClear();
    diagnosticsServiceStub.acknowledgeError.mockClear();
    glitchtipServiceStub.getRecentEvents.mockClear();
    autoIssuesServiceStub.list.mockClear();
    autoIssuesServiceStub.resync.mockClear();
    autoIssuesServiceStub.flushCache.mockClear();
  });

  it('exposes the exact Pyroscope dashboard base URL', async () => {
    // Pins the literal so a mutation of the URL string is caught (the frontend
    // opens this URL in a new tab; a wrong host would silently break the link).
    diagnosticsServiceStub.getErrors.mockReturnValue(of([]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ErrorLogComponent);
    expect(fixture.componentInstance.pyroscopeBaseUrl).toBe('http://localhost:4040');
  });

  it('groups multiple rows with the same fingerprint into one expansion panel', async () => {
    diagnosticsServiceStub.getErrors.mockReturnValue(
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
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
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
      error_message: 'OperationalError: connection failed: connection to server at "172.18.0.8" port 5432 failed.',
      how_to_fix: 'Check the database container and retry the job.',
      raw_exception: 'Traceback (most recent call last):\nOperationalError',
    });
    diagnosticsServiceStub.getErrors.mockReturnValue(of([detailedError]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
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

    const header = fixture.nativeElement.querySelector('mat-expansion-panel-header') as HTMLElement;
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
    diagnosticsServiceStub.getErrors.mockReturnValue(of([]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));

    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
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
    expect(autoIssuesServiceStub.list.mock.calls.length).toBe(1);
    expect(autoIssuesServiceStub.list.mock.calls[0]).toEqual([{ status: 'open' }]);
    const everyCall = autoIssuesServiceStub.list.mock.calls;
    const fetchedResolved = everyCall.some((args) => args[0]?.status === 'resolved');
    expect(fetchedResolved).toBe(false);
  });

  it('renders the GlitchTip outbound link on grouped GlitchTip rows', async () => {
    diagnosticsServiceStub.getErrors.mockReturnValue(of([]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(
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
        provideHttpClient(withXhr()),
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

    const header = fixture.nativeElement.querySelector('mat-expansion-panel-header') as HTMLElement;
    header.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.glitchtip-link-button') as HTMLAnchorElement;
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
    diagnosticsServiceStub.getErrors.mockReturnValue(of([]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
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
    vi.spyOn(c, 'loadErrors').mockReturnValue(undefined as never);
    vi.spyOn(c, 'loadGlitchtipEvents').mockReturnValue(undefined as never);
    diagnosticsServiceStub.acknowledgeError.mockReturnValue(of({ status: 'acknowledged' }));
    c.acknowledgeError(makeError({ source: 'glitchtip' }));
    expect(c.loadErrors).toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).toHaveBeenCalled();
  });

  it('acknowledgeError does not reload glitchtip events if source is internal', async () => {
    const c = await buildComponent();
    vi.spyOn(c, 'loadErrors').mockReturnValue(undefined as never);
    vi.spyOn(c, 'loadGlitchtipEvents').mockReturnValue(undefined as never);
    diagnosticsServiceStub.acknowledgeError.mockReturnValue(of({ status: 'acknowledged' }));
    c.acknowledgeError(makeError({ source: 'internal' }));
    expect(c.loadErrors).toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).not.toHaveBeenCalled();
  });

  it('acknowledgeError reloads errors even if acknowledgeError fails', async () => {
    const c = await buildComponent();
    vi.spyOn(c, 'loadErrors').mockReturnValue(undefined as never);
    diagnosticsServiceStub.acknowledgeError.mockReturnValue(throwError(() => new Error('fail')));
    c.acknowledgeError(makeError({ source: 'internal' }));
    expect(c.loadErrors).toHaveBeenCalled();
  });

  it('resync populates resyncStatus and resyncBusy on success and failure', async () => {
    const c = await buildComponent();

    autoIssuesServiceStub.resync.mockReturnValue(of({ open_count: 5 }));
    c.resync();
    expect(c.resyncBusy).toBe(false);
    expect(c.resyncStatus).toBe('Synced — 5 open issues now');

    autoIssuesServiceStub.resync.mockReturnValue(throwError(() => ({ statusText: 'Bad Gateway' })));
    c.resync();
    expect(c.resyncBusy).toBe(false);
    expect(c.resyncStatus).toBe('Resync failed: Bad Gateway');

    autoIssuesServiceStub.resync.mockReturnValue(throwError(() => ({})));
    c.resync();
    expect(c.resyncBusy).toBe(false);
    expect(c.resyncStatus).toBe('Resync failed: unknown');
  });

  it('flushCache populates resyncStatus and flushBusy on success and failure', async () => {
    const c = await buildComponent();
    const markForCheckSpy = vi.spyOn((c as any).cdr, 'markForCheck');

    autoIssuesServiceStub.flushCache.mockReturnValue(of({ flushed_rows: 10 }));
    c.flushCache();
    expect(c.flushBusy).toBe(false);
    expect(c.resyncStatus).toBe('Flushed 10 stale rows');
    expect(markForCheckSpy).toHaveBeenCalled();
    markForCheckSpy.mockClear();

    autoIssuesServiceStub.flushCache.mockReturnValue(throwError(() => ({ statusText: 'Server Error' })));
    c.flushCache();
    expect(c.flushBusy).toBe(false);
    expect(c.resyncStatus).toBe('Flush failed: Server Error');
    expect(markForCheckSpy).toHaveBeenCalled();
    markForCheckSpy.mockClear();

    autoIssuesServiceStub.flushCache.mockReturnValue(throwError(() => ({})));
    c.flushCache();
    expect(c.flushBusy).toBe(false);
    expect(c.resyncStatus).toBe('Flush failed: unknown');
    expect(markForCheckSpy).toHaveBeenCalled();
  });

  it('flushCache subscription is cleaned up when component is destroyed', async () => {
    diagnosticsServiceStub.getErrors.mockReturnValue(of([]));
    glitchtipServiceStub.getRecentEvents.mockReturnValue(of([]));
    await TestBed.configureTestingModule({
      imports: [ErrorLogComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideRouter([]),
        { provide: DiagnosticsService, useValue: diagnosticsServiceStub },
        { provide: GlitchtipService, useValue: glitchtipServiceStub },
        { provide: AutoIssuesService, useValue: autoIssuesServiceStub },
        { provide: VisibilityGateService, useValue: visibilityGateStub },
      ],
    }).compileComponents();

    const flushSubject = new Subject<any>();
    autoIssuesServiceStub.flushCache.mockReturnValue(flushSubject.asObservable());

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

  it('showJobTypeAndStatusFilters returns false for glitchtip, auto-issues, and pyroscope tabs, and true otherwise', async () => {
    const c = await buildComponent();

    // Should be false for these tabs
    c.selectedTabIndex = 1; // GLITCHTIP_TAB_INDEX
    expect(c.showJobTypeAndStatusFilters).toBe(false);

    c.selectedTabIndex = 3; // AUTO_ISSUES_TAB_INDEX
    expect(c.showJobTypeAndStatusFilters).toBe(false);

    c.selectedTabIndex = 4; // PYROSCOPE_TAB_INDEX
    expect(c.showJobTypeAndStatusFilters).toBe(false);

    // Should be true for other tabs
    c.selectedTabIndex = 0; // internal
    expect(c.showJobTypeAndStatusFilters).toBe(true);

    c.selectedTabIndex = 2; // all
    expect(c.showJobTypeAndStatusFilters).toBe(true);
  });

  // Kills surviving Stryker mutants AutoIssues #19047 (ConditionalExpression),
  // #19048 (BooleanLiteral) on uniqueJobTypes block and #19049 (BlockStatement)
  // on unreviewedCount block. These getters had no assertions so any mutation
  // that changed their return value survived undetected.
  it('uniqueJobTypes returns sorted deduplicated job types', async () => {
    const c = await buildComponent();
    c.errors = [
      makeError({ id: 1, job_type: 'sync' }),
      makeError({ id: 2, job_type: 'import' }),
      makeError({ id: 3, job_type: 'sync' }),
      makeError({ id: 4, job_type: 'embed' }),
    ];
    expect(c.uniqueJobTypes).toEqual(['embed', 'import', 'sync']);
  });

  it('uniqueJobTypes returns empty array when there are no errors', async () => {
    const c = await buildComponent();
    c.errors = [];
    expect(c.uniqueJobTypes).toEqual([]);
  });

  it('unreviewedCount returns count of unacknowledged errors only', async () => {
    const c = await buildComponent();
    c.errors = [
      makeError({ id: 1, acknowledged: false }),
      makeError({ id: 2, acknowledged: true }),
      makeError({ id: 3, acknowledged: false }),
    ];
    expect(c.unreviewedCount).toBe(2);
  });

  it('unreviewedCount returns 0 when all errors are acknowledged', async () => {
    const c = await buildComponent();
    c.errors = [makeError({ id: 1, acknowledged: true }), makeError({ id: 2, acknowledged: true })];
    expect(c.unreviewedCount).toBe(0);
  });

  it('filteredErrors excludes acknowledged errors when filterAcknowledged is unreviewed', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0;
    c.errors = [
      makeError({ id: 1, source: 'internal', acknowledged: false }),
      makeError({ id: 2, source: 'internal', acknowledged: true }),
    ];
    c.filterJobType = '';
    c.filterAcknowledged = 'unreviewed';
    const result = c.filteredErrors;
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(1);
  });

  it('filteredErrors excludes unacknowledged errors when filterAcknowledged is reviewed', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0;
    c.errors = [
      makeError({ id: 1, source: 'internal', acknowledged: false }),
      makeError({ id: 2, source: 'internal', acknowledged: true }),
    ];
    c.filterJobType = '';
    c.filterAcknowledged = 'reviewed';
    const result = c.filteredErrors;
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(2);
  });

  it('filteredErrors filters by job type when filterJobType is set', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0;
    c.errors = [
      makeError({ id: 1, source: 'internal', job_type: 'pipeline', acknowledged: false }),
      makeError({ id: 2, source: 'internal', job_type: 'import', acknowledged: false }),
    ];
    c.filterJobType = 'pipeline';
    c.filterAcknowledged = 'unreviewed';
    const result = c.filteredErrors;
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(1);
  });

  it('uniqueJobTypes returns unique sorted job types from all errors', async () => {
    const c = await buildComponent();
    c.errors = [
      makeError({ job_type: 'pipeline' }),
      makeError({ job_type: 'import' }),
      makeError({ job_type: 'pipeline' }),
    ];
    expect(c.uniqueJobTypes).toEqual(['import', 'pipeline']);
  });

  it('uniqueJobTypes values are job_type strings not acknowledged booleans', async () => {
    const c = await buildComponent();
    c.errors = [
      makeError({ job_type: 'crawler', acknowledged: false }),
      makeError({ job_type: 'sync', acknowledged: true }),
    ];
    const types = c.uniqueJobTypes;
    expect(types).toContain('crawler');
    expect(types).toContain('sync');
    expect(types.every((t) => typeof t === 'string' && t !== '')).toBe(true);
  });

  it('groupedErrors uses filteredErrors not raw errors', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0;
    c.errors = [
      makeError({ id: 1, source: 'glitchtip', job_type: 'pipeline', fingerprint: 'fp-gt' }),
      makeError({ id: 2, source: 'internal', job_type: 'pipeline', fingerprint: 'fp-int' }),
    ];
    c.filterJobType = '';
    c.filterAcknowledged = 'all';
    // filteredErrors excludes glitchtip when tab=0 (non-glitchtip tab)
    const filtered = c.filteredErrors;
    const grouped = c.groupedErrors;
    // Each ErrorGroup.totalCount is the occurrence count for that fingerprint bucket.
    // The total across all groups equals the number of filteredErrors entries.
    const groupedCount = grouped.reduce((sum, g) => sum + g.totalCount, 0);
    expect(groupedCount).toBe(filtered.length);
  });

  it('filteredErrors excludes glitchtip errors when selectedTabIndex is not ALL_TAB_INDEX', async () => {
    const c = await buildComponent();
    c.selectedTabIndex = 0; // GLITCHTIP_TAB_INDEX is 1, ALL_TAB_INDEX is 2
    c.errors = [makeError({ id: 1, source: 'glitchtip' }), makeError({ id: 2, source: 'internal' })];
    c.filterJobType = '';
    c.filterAcknowledged = 'all';
    const result = c.filteredErrors;
    expect(result.length).toBe(1);
    expect(result[0].id).toBe(2);
  });

  // Added tests for missing branches

  it('openGlitchtip opens window with glitchtipBaseUrl', async () => {
    const c = await buildComponent();
    vi.spyOn(window, 'open').mockImplementation(() => null);
    c.openGlitchtip();
    expect(window.open).toHaveBeenCalledWith(c.glitchtipBaseUrl, '_blank', 'noopener,noreferrer');
  });

  it('openGlitchtip does nothing if glitchtipBaseUrl is empty', async () => {
    const c = await buildComponent();
    Object.defineProperty(c, 'glitchtipBaseUrl', { value: '' });
    vi.spyOn(window, 'open').mockImplementation(() => null);
    c.openGlitchtip();
    expect(window.open).not.toHaveBeenCalled();
  });

  it('openPyroscope opens window with pyroscopeBaseUrl', async () => {
    const c = await buildComponent();
    vi.spyOn(window, 'open').mockImplementation(() => null);
    c.openPyroscope();
    expect(window.open).toHaveBeenCalledWith(c.pyroscopeBaseUrl, '_blank', 'noopener,noreferrer');
  });

  it('onTabChange updates selectedTabIndex and calls appropriate load methods', async () => {
    const c = await buildComponent();
    vi.spyOn(c, 'loadGlitchtipEvents').mockImplementation(() => {});
    vi.spyOn(c, 'loadAutoIssues').mockImplementation(() => {});

    c.onTabChange(1); // GLITCHTIP_TAB_INDEX
    expect(c.selectedTabIndex).toBe(1);
    expect(c.loadGlitchtipEvents).toHaveBeenCalled();
    expect(c.loadAutoIssues).not.toHaveBeenCalled();

    vi.mocked(c.loadGlitchtipEvents).mockClear();
    vi.mocked(c.loadAutoIssues).mockClear();

    c.onTabChange(3); // AUTO_ISSUES_TAB_INDEX
    expect(c.selectedTabIndex).toBe(3);
    expect(c.loadAutoIssues).toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).not.toHaveBeenCalled();

    vi.mocked(c.loadGlitchtipEvents).mockClear();
    vi.mocked(c.loadAutoIssues).mockClear();

    c.onTabChange(0); // internal tab
    expect(c.selectedTabIndex).toBe(0);
    expect(c.loadAutoIssues).not.toHaveBeenCalled();
    expect(c.loadGlitchtipEvents).not.toHaveBeenCalled();
  });

  it('loadGlitchtipEvents logs warning on error', async () => {
    const c = await buildComponent();
    const error = new Error('gt error');
    glitchtipServiceStub.getRecentEvents.mockReturnValue(throwError(() => error));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    c.loadGlitchtipEvents();
    expect(console.warn).toHaveBeenCalledWith('glitchtip events failed', error);
  });

  it('startGlitchtipPoll handles fetch error without crashing timer', async () => {
    vi.useFakeTimers();
    vi.spyOn(visibilityGateStub, 'whileLoggedInAndVisible').mockImplementation(((cb: any) => cb()) as any);
    
    const c = await buildComponent();
    
    const error = new Error('gt poll error');
    glitchtipServiceStub.getRecentEvents.mockReturnValue(throwError(() => error));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    c.ngOnInit(); // triggers startGlitchtipPoll
    
    await vi.advanceTimersByTimeAsync(30000);
    
    expect(console.warn).toHaveBeenCalledWith('glitchtip poll fetch failed', error);
    
    vi.useRealTimers();
    vi.mocked(visibilityGateStub.whileLoggedInAndVisible).mockRestore();
  });

  it('loadErrors sets loading to false on error', async () => {
    const c = await buildComponent();
    diagnosticsServiceStub.getErrors.mockReturnValue(throwError(() => new Error('err')));
    c.loading = true;
    c.loadErrors();
    expect(c.loading).toBe(false);
  });
});
