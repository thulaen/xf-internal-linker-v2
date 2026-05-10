import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { MatSnackBar } from '@angular/material/snack-bar';
import { BehaviorSubject, of, throwError } from 'rxjs';

import { ScheduledUpdatesComponent } from './scheduled-updates.component';
import { ScheduledUpdatesService } from './scheduled-updates.service';

const stubJob = {
  id: 1,
  key: 'demo',
  display_name: 'Demo Job',
  priority: 'medium' as const,
  state: 'pending' as const,
  progress_pct: 0,
  current_message: '',
  started_at: null,
  finished_at: null,
  last_run_at: null,
  last_success_at: null,
  scheduled_for: null,
  cadence_seconds: 60,
  duration_estimate_sec: 1,
  pause_token: false,
  log_tail: '',
  created_at: '2026-04-30T00:00:00Z',
  updated_at: '2026-04-30T00:00:00Z',
};

describe('ScheduledUpdatesComponent', () => {
  let fixture: ComponentFixture<ScheduledUpdatesComponent>;
  let component: ScheduledUpdatesComponent;
  let httpMock: HttpTestingController;
  const snackStub = { open: () => undefined };
  const svcStub = {
    jobs$: new BehaviorSubject([stubJob]),
    alerts$: new BehaviorSubject([]),
    windowStatus$: new BehaviorSubject(null),
    refreshJobs: () => of([stubJob]),
    refreshAlerts: () => of([]),
    refreshWindowStatus: () => of(null),
    startRealtimeStream: () => undefined,
    stopRealtimeStream: () => undefined,
    pauseJob: () => of({ ok: true }),
    resumeJob: () => of({ ok: true }),
    cancelJob: () => of({ ok: true }),
    runNow: () => of({ ok: true }),
    acknowledgeAlert: () => of({ ok: true }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ScheduledUpdatesComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: ScheduledUpdatesService, useValue: svcStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    })
      .overrideComponent(ScheduledUpdatesComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(ScheduledUpdatesComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('subscribes to jobs and renders without throwing', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.jobs.length).toBe(1);
    expect(component.loading).toBeFalse();
    expect(component.runningJob).toBeNull();
    expect(component.pendingJobs.length).toBe(1);
  });

  it('runNow calls service and snacks success', () => {
    fixture.detectChanges();
    const spy = spyOn(svcStub, 'runNow').and.callThrough();
    component.runNow(stubJob);
    expect(spy).toHaveBeenCalled();
  });

  it('handles failure of refreshJobs by clearing loading', () => {
    const failing = {
      ...svcStub,
      refreshJobs: () => throwError(() => new Error('x')),
    };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ScheduledUpdatesComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: ScheduledUpdatesService, useValue: failing },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    }).overrideComponent(ScheduledUpdatesComponent, {
      set: { template: '<div></div>' },
    });
    const fx = TestBed.createComponent(ScheduledUpdatesComponent);
    fx.detectChanges();
    expect(fx.componentInstance.loading).toBeFalse();
  });
});
