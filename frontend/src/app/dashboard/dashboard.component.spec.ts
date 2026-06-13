import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY, of, throwError } from 'rxjs';

import { DashboardComponent } from './dashboard.component';
import { DashboardData, DashboardService } from './dashboard.service';
import { SuggestionService } from '../review/suggestion.service';
import { SyncService } from '../jobs/sync.service';
import { PulseService } from '../core/services/pulse.service';
import { PerformanceModeService } from '../core/services/performance-mode.service';
import { DashboardModesService } from '../core/services/dashboard-modes.service';

const EMPTY_DATA: DashboardData = {
  suggestion_counts: { pending: 0, approved: 0, rejected: 0, applied: 0, total: 0 },
  content_count: 5,
  open_broken_links: 0,
  last_sync: null,
  pipeline_runs: [],
  recent_imports: [],
  system_health: { status: 'healthy', summary: {}, total_monitored: 0 },
} as DashboardData;

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let component: DashboardComponent;
  let httpMock: HttpTestingController;
  let dashSvc: SpyObj<DashboardService>;

  beforeEach(async () => {
    dashSvc = createSpyObj<DashboardService>(['refresh', 'invalidate', 'updateOpenBrokenLinks']);
    dashSvc.refresh.mockReturnValue(of(EMPTY_DATA));

    // Skip the heavy template — the dashboard imports 50+ child standalone
    // components, each with its own services. Override compiles a no-op
    // template instead so we exercise the TS class without dragging in
    // every child's dependency tree.
    TestBed.overrideComponent(DashboardComponent, {
      set: { template: '<div data-test="dashboard-stub"></div>', imports: [], styles: [] },
    });

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideRouter([{ path: 'jobs', children: [] }]),
        provideNoopAnimations(),
        { provide: DashboardService, useValue: dashSvc },
        { provide: SuggestionService, useValue: { startPipeline: () => of({ run_id: 'run-1' }) } },
        {
          provide: SyncService,
          useValue: {
            getSourceStatus: () => of({ api: false, wp: false }),
            triggerApiSync: () => of({ job_id: 'j1', source: 'api', mode: 'full' }),
            resumeJob: () => of({ status: 'pending' }),
          },
        },
        { provide: PulseService, useValue: { events$: EMPTY } },
        { provide: PerformanceModeService, useValue: { setMode: vi.fn() } },
        { provide: DashboardModesService, useValue: { calmMode: () => false } },
      ],
      schemas: [CUSTOM_ELEMENTS_SCHEMA],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.match(() => true).forEach((req) => req.flush({}));
    httpMock.verify();
  });

  it('renders and loads dashboard data on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({}));
    expect(component).toBeTruthy();
    expect(dashSvc.refresh).toHaveBeenCalled();
    expect(component.data).toBe(EMPTY_DATA);
    expect(component.loading).toBe(false);
  });

  it('catchUpSync handles "no sources configured" path', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({}));
    component.catchUpSync();
    expect(component.syncing).toBe(false);
  });

  it('stateColor + stateIcon return mapping for known states', () => {
    expect(component.stateColor('completed')).toBe('success');
    expect(component.stateColor('failed')).toBe('warn');
    expect(component.stateIcon('running')).toBe('sync');
    expect(component.stateIcon('queued')).toBe('schedule');
  });

  it('handles refresh failure by clearing loading and not crashing', () => {
    dashSvc.refresh.mockReturnValue(throwError(() => new Error('500')));
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({}));
    expect(component.loading).toBe(false);
  });

  // GSC summary tile getters (Part 5). They read `component.data` only, so we
  // set it directly and assert the tile rows + tone mapping. Empty data yields
  // empty rows so the cards collapse rather than showing zeros for nothing.
  describe('summary tile getters', () => {
    it('return empty arrays when there is no data', () => {
      component.data = null as unknown as DashboardData;
      expect(component.reviewTiles).toEqual([]);
      expect(component.contentTiles).toEqual([]);
      expect(component.healthTiles).toEqual([]);
      expect(component.pipelineTiles).toEqual([]);
    });

    it('reviewTiles map the four suggestion counts with their tones', () => {
      component.data = {
        ...EMPTY_DATA,
        suggestion_counts: { pending: 3, approved: 2, rejected: 1, applied: 4, total: 10 },
      } as DashboardData;
      expect(component.reviewTiles).toEqual([
        { label: 'Pending', value: 3, tone: 'blue' },
        { label: 'Approved', value: 2, tone: 'green' },
        { label: 'Applied live', value: 4, tone: 'purple' },
        { label: 'Total', value: 10, tone: 'grey' },
      ]);
    });

    it('healthTiles tint the status tone green only when healthy', () => {
      component.data = {
        ...EMPTY_DATA,
        system_health: { status: 'healthy', summary: {}, total_monitored: 7 },
      } as DashboardData;
      expect(component.healthTiles[0]).toEqual({ label: 'Status', value: 'healthy', tone: 'green' });
      component.data = {
        ...EMPTY_DATA,
        system_health: { status: 'warning', summary: {}, total_monitored: 7 },
      } as DashboardData;
      expect(component.healthTiles[0]).toEqual({ label: 'Status', value: 'warning', tone: 'amber' });
    });
  });

  // The single "attention" banner. Priority order: system health → broken
  // links → pending reviews → all clear. Each branch must own headline, tone,
  // and the action link to the page that fixes that exact issue.
  describe('attention banner', () => {
    it('is empty info when there is no data', () => {
      component.data = null as unknown as DashboardData;
      expect(component.attention).toEqual({
        tone: 'info',
        headline: '',
        detail: '',
        actionLabel: null,
        actionLink: null,
      });
    });

    it('prioritises unhealthy system health over everything else', () => {
      component.data = {
        ...EMPTY_DATA,
        system_health: { status: 'warning', summary: {}, total_monitored: 1 },
        open_broken_links: 5,
        suggestion_counts: { pending: 9, approved: 0, rejected: 0, applied: 0, total: 9 },
      } as DashboardData;
      const a = component.attention;
      expect(a.tone).toBe('warning');
      expect(a.actionLink).toBe('/health');
    });

    it('flags broken links with correct singular/plural wording', () => {
      component.data = { ...EMPTY_DATA, open_broken_links: 1 } as DashboardData;
      expect(component.attention.headline).toBe('1 broken link to fix');
      expect(component.attention.actionLink).toBe('/link-health');
      component.data = { ...EMPTY_DATA, open_broken_links: 3 } as DashboardData;
      expect(component.attention.headline).toBe('3 broken links to fix');
    });

    it('falls back to pending reviews, then to the all-clear state', () => {
      component.data = {
        ...EMPTY_DATA,
        suggestion_counts: { pending: 2, approved: 0, rejected: 0, applied: 0, total: 2 },
      } as DashboardData;
      expect(component.attention.actionLink).toBe('/review');
      expect(component.attention.headline).toBe('2 suggestions waiting for review');

      component.data = { ...EMPTY_DATA } as DashboardData;
      const clear = component.attention;
      expect(clear.tone).toBe('success');
      expect(clear.actionLabel).toBeNull();
    });
  });
});
