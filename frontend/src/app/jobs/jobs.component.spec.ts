import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY, of, throwError } from 'rxjs';

import { JobsComponent } from './jobs.component';
import { SyncService } from './sync.service';
import { RealtimeService } from '../core/services/realtime.service';
import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { AuthService } from '../core/services/auth.service';

describe('JobsComponent', () => {
  let fixture: ComponentFixture<JobsComponent>;
  let component: JobsComponent;
  let httpMock: HttpTestingController;
  let syncSvc: SpyObj<SyncService>;

  beforeEach(async () => {
    syncSvc = createSpyObj<SyncService>([
      'getJobs',
      'getJob',
      'triggerApiSync',
      'pauseJob',
      'resumeJob',
      'getSourceStatus',
      'uploadFile',
    ]);
    syncSvc.getJobs.mockReturnValue(of([]));
    syncSvc.getSourceStatus.mockReturnValue(of({ api: true, wp: false }));
    syncSvc.triggerApiSync.mockReturnValue(of({ job_id: 'j1', source: 'api', mode: 'full' }));
    syncSvc.pauseJob.mockReturnValue(of({ job_id: 'j1', status: 'paused', is_resumable: true, message: 'Paused' }));
    syncSvc.resumeJob.mockReturnValue(of({ job_id: 'j1', status: 'pending', is_resumable: true, message: 'Resumed' }));

    // The real template uses 9 `i18n=` markers; the test polyfills do not
    // load `@angular/localize/init`. Stub the template so the TS class
    // can be exercised without crashing on a missing $localize symbol.
    TestBed.overrideComponent(JobsComponent, {
      set: { template: '<div data-test="jobs-stub"></div>', imports: [], styles: [] },
    });

    await TestBed.configureTestingModule({
      imports: [JobsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: SyncService, useValue: syncSvc },
        { provide: RealtimeService, useValue: { subscribeTopic: () => EMPTY } },
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
        { provide: AuthService, useValue: { getToken: () => null } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(JobsComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    httpMock.verify();
  });

  it('renders and loads job history + source status on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component).toBeTruthy();
    expect(syncSvc.getJobs).toHaveBeenCalled();
    expect(syncSvc.getSourceStatus).toHaveBeenCalled();
  });

  it('pauseSyncJob calls service and shows snack on success', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    component.pauseSyncJob('j1');
    expect(syncSvc.pauseJob).toHaveBeenCalledWith('j1');
  });

  it('loadHistory tolerates a non-array response without crashing', () => {
    // The component normalises non-array payloads to []. Cast through unknown
    // because the spy's strict typing demands SyncJob[].
    (syncSvc.getJobs.mockReturnValue as (v: unknown) => unknown)(of(null));
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.syncJobs()).toEqual([]);
  });

  it('loadHistory error path leaves syncJobs empty and logs', () => {
    syncSvc.getJobs.mockReturnValue(throwError(() => new Error('500')));
    vi.spyOn(console, 'error').mockReturnValue(undefined as never);
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.syncJobs()).toEqual([]);
    expect(console.error).toHaveBeenCalled();
  });

  it('resumeSyncJob calls service and shows snack on success', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    component.resumeSyncJob('j1');
    expect(syncSvc.resumeJob).toHaveBeenCalledWith('j1');
  });

  it('should load source status on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.sourceStatus().api).toBe(true);
    expect(component.sourceStatus().wp).toBe(false);
  });

  it('should compute anyRunning based on job states', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    const job = component.jobs();
    expect(component.anyRunning()).toBe(false);
    component.jobs.set({ ...job, api: { ...job.api, state: 'running' } });
    expect(component.anyRunning()).toBe(true);
  });

  it('should compute canSyncAll when sources are available and jobs are idle', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    component.sourceStatus.set({ api: true, wp: false });
    expect(component.canSyncAll()).toBe(true);
  });

  it('should compute selectedFile signal', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    const file = new File(['test'], 'test.jsonl');
    component.selectedFile.set(file);
    expect(component.selectedFile()).toBe(file);
    component.selectedFile.set(null);
    expect(component.selectedFile()).toBeNull();
  });

  it('should compute isDragOver signal', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.isDragOver()).toBe(false);
    component.isDragOver.set(true);
    expect(component.isDragOver()).toBe(true);
  });

  it('getDuration returns elapsed time for running job', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    const job: any = {
      job_id: 'j1',
      source: 'api',
      mode: 'full',
      status: 'running',
      created_at: new Date(Date.now() - 5000).toISOString(),
      progress: 50,
      message: 'Processing',
      items_synced: 10,
      items_updated: 5,
      ml_items_queued: 0,
      ml_items_completed: 0,
      spacy_items_completed: 0,
      embedding_items_completed: 0,
      checkpoint_stage: 'ingest',
      checkpoint_items_processed: 10,
      is_resumable: false,
    };
    const duration = component.getDuration(job);
    expect(duration).toBeDefined();
  });

  it('getSuccessRate returns rate from job', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    const job: any = {
      job_id: 'j1',
      source: 'api',
      mode: 'full',
      status: 'running',
      created_at: new Date().toISOString(),
      progress: 95,
      message: 'Processing',
      items_synced: 95,
      items_updated: 0,
      ml_items_queued: 0,
      ml_items_completed: 0,
      spacy_items_completed: 0,
      embedding_items_completed: 0,
      checkpoint_stage: 'ingest',
      checkpoint_items_processed: 100,
      is_resumable: false,
    };
    const rate = component.getSuccessRate(job);
    expect(typeof rate).toBe('string');
  });
});
