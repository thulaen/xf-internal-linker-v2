import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
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
  let dashSvc: jasmine.SpyObj<DashboardService>;

  beforeEach(async () => {
    dashSvc = jasmine.createSpyObj<DashboardService>('DashboardService', [
      'refresh', 'invalidate', 'updateOpenBrokenLinks',
    ]);
    dashSvc.refresh.and.returnValue(of(EMPTY_DATA));

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
        provideHttpClient(),
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
        { provide: PerformanceModeService, useValue: { setMode: jasmine.createSpy('setMode') } },
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
    expect(component.loading).toBeFalse();
  });

  it('catchUpSync handles "no sources configured" path', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({}));
    component.catchUpSync();
    expect(component.syncing).toBeFalse();
  });

  it('stateColor + stateIcon return mapping for known states', () => {
    expect(component.stateColor('completed')).toBe('success');
    expect(component.stateColor('failed')).toBe('warn');
    expect(component.stateIcon('running')).toBe('sync');
    expect(component.stateIcon('queued')).toBe('schedule');
  });

  it('handles refresh failure by clearing loading and not crashing', () => {
    dashSvc.refresh.and.returnValue(throwError(() => new Error('500')));
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({}));
    expect(component.loading).toBeFalse();
  });
});
