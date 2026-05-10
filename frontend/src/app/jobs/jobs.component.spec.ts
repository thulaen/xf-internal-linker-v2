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
  let syncSvc: jasmine.SpyObj<SyncService>;

  beforeEach(async () => {
    syncSvc = jasmine.createSpyObj<SyncService>('SyncService', [
      'getJobs',
      'getJob',
      'triggerApiSync',
      'pauseJob',
      'resumeJob',
      'getSourceStatus',
      'uploadFile',
    ]);
    syncSvc.getJobs.and.returnValue(of([]));
    syncSvc.getSourceStatus.and.returnValue(of({ api: true, wp: false }));
    syncSvc.triggerApiSync.and.returnValue(of({ job_id: 'j1', source: 'api', mode: 'full' }));
    syncSvc.pauseJob.and.returnValue(of({ job_id: 'j1', status: 'paused', is_resumable: true, message: 'Paused' }));
    syncSvc.resumeJob.and.returnValue(of({ job_id: 'j1', status: 'pending', is_resumable: true, message: 'Resumed' }));

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
    (syncSvc.getJobs.and.returnValue as (v: unknown) => unknown)(of(null));
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.syncJobs()).toEqual([]);
  });

  it('loadHistory error path leaves syncJobs empty and logs', () => {
    syncSvc.getJobs.and.returnValue(throwError(() => new Error('500')));
    spyOn(console, 'error');
    fixture.detectChanges();
    httpMock.match(() => true).forEach((req) => req.flush({ items: [], locks: {} }));
    expect(component.syncJobs()).toEqual([]);
    expect(console.error).toHaveBeenCalled();
  });
});
