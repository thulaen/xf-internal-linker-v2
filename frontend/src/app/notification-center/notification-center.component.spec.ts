import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { Subject, of, throwError } from 'rxjs';

import { NotificationCenterComponent } from './notification-center.component';
import { NotificationService } from '../core/services/notification.service';

const stubAlert = {
  id: 1,
  alert_id: 'a1',
  event_type: 'job.failed',
  source_area: 'pipeline',
  severity: 'error' as const,
  status: 'unread' as const,
  title: 'Boom',
  message: 'Something broke',
  dedupe_key: 'k',
  occurrence_count: 1,
  related_object_type: '',
  related_object_id: '',
  related_route: '/diagnostics',
  payload: {},
  error_log_id: null,
  first_seen_at: '2026-04-30T00:00:00Z',
  last_seen_at: '2026-04-30T00:00:00Z',
  suppressed_until: null,
  read_at: null,
  acknowledged_at: null,
  resolved_at: null,
  created_at: '2026-04-30T00:00:00Z',
  updated_at: '2026-04-30T00:00:00Z',
};

describe('NotificationCenterComponent', () => {
  let fixture: ComponentFixture<NotificationCenterComponent>;
  let component: NotificationCenterComponent;
  let httpMock: HttpTestingController;
  const svcStub = {
    newAlert$: new Subject<unknown>(),
    loadAlerts: () =>
      of({ count: 1, next: null, previous: null, results: [stubAlert] }),
    acknowledgeAll: () => of({ ok: true }),
    acknowledge: () => of({ ok: true }),
    markRead: () => of({ ok: true }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NotificationCenterComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: NotificationService, useValue: svcStub },
      ],
    })
      .overrideComponent(NotificationCenterComponent, {
        set: { template: '<div></div>' },
      })
      .compileComponents();
    fixture = TestBed.createComponent(NotificationCenterComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('loads alerts on init', () => {
    fixture.detectChanges();
    httpMock.match(() => true).forEach((r) => r.flush({}));
    expect(component.alerts().length).toBe(1);
    expect(component.severityIcon('error')).toBe('error');
    expect(component.severityIcon('unknown')).toBe('notifications');
  });

  it('open/close emit the right events', () => {
    fixture.detectChanges();
    let lastEmit: boolean | null = null;
    component.openChange.subscribe((v) => (lastEmit = v));
    component.openPanel();
    expect(lastEmit).toBe(true);
    component.close();
    expect(lastEmit).toBe(false);
  });

  it('handles failed loadAlerts by clearing loading', () => {
    const failing = {
      ...svcStub,
      loadAlerts: () => throwError(() => new Error('x')),
    };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [NotificationCenterComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: NotificationService, useValue: failing },
      ],
    }).overrideComponent(NotificationCenterComponent, {
      set: { template: '<div></div>' },
    });
    const fx = TestBed.createComponent(NotificationCenterComponent);
    fx.detectChanges();
    expect(fx.componentInstance.loading()).toBe(false);
    expect(fx.componentInstance.alerts().length).toBe(0);
  });
});
