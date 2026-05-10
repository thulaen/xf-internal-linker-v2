import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { NotificationsTabComponent } from './notifications-tab.component';
import {
  NotificationPreferences,
  NotificationService,
} from '../../core/services/notification.service';

const DEFAULT_PREFS: NotificationPreferences = {
  desktop_enabled: true,
  sound_enabled: true,
  quiet_hours_enabled: false,
  quiet_hours_start: '22:00',
  quiet_hours_end: '07:00',
  min_desktop_severity: 'warning',
  min_sound_severity: 'error',
  enable_job_completed: true,
  enable_job_failed: true,
  enable_job_stalled: true,
  enable_model_status: true,
  enable_gsc_spikes: true,
  toast_enabled: true,
  toast_min_severity: 'warning',
  duplicate_cooldown_seconds: 900,
  job_stalled_default_minutes: 15,
  gsc_spike_min_impressions_delta: 50,
  gsc_spike_min_clicks_delta: 5,
  gsc_spike_min_relative_lift: 0.5,
};

describe('NotificationsTabComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NotificationsTabComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        // Use the real NotificationService so the load + save HTTP calls go
        // through the actual `/api/settings/notifications/` endpoint paths,
        // which the spec asserts on via HttpTestingController.
        NotificationService,
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function flushInitialLoad(): void {
    const req = httpMock.expectOne('/api/settings/notifications/');
    expect(req.request.method).toBe('GET');
    req.flush(DEFAULT_PREFS);
  }

  it('renders the four notification cards without error', () => {
    const fixture = TestBed.createComponent(NotificationsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('#alert-delivery')).withContext('alert delivery card').not.toBeNull();
    expect(root.querySelector('#quiet-hours')).withContext('quiet hours card').not.toBeNull();
    expect(root.querySelector('#settings-event-subscriptions')).withContext('event subscriptions card').not.toBeNull();
    expect(root.querySelector('#settings-send-test-alert')).withContext('test alert card').not.toBeNull();
  });

  it('updates local preferences when a checkbox is toggled', () => {
    const fixture = TestBed.createComponent(NotificationsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    expect(cmp.notifPrefs.toast_enabled).toBeTrue();

    cmp.notifPrefs.toast_enabled = false;
    cmp.markDirty();
    fixture.detectChanges();

    expect(cmp.notifPrefs.toast_enabled).toBeFalse();
  });

  it('sends PUT to /api/settings/notifications/ with the current payload on save', () => {
    const fixture = TestBed.createComponent(NotificationsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    cmp.notifPrefs.quiet_hours_enabled = true;
    cmp.saveNotifPrefs();

    const req = httpMock.expectOne('/api/settings/notifications/');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body.quiet_hours_enabled).toBeTrue();
    expect(req.request.body.toast_enabled).toBeTrue();
    req.flush({ ...DEFAULT_PREFS, quiet_hours_enabled: true });

    expect(cmp.savingNotifPrefs()).toBeFalse();
  });

  it('emits dirtyChanged true after a state change and false after a successful save', () => {
    const fixture = TestBed.createComponent(NotificationsTabComponent);
    fixture.detectChanges();
    flushInitialLoad();
    fixture.detectChanges();

    const cmp = fixture.componentInstance;
    const emitted: boolean[] = [];
    cmp.dirtyChanged.subscribe((v) => emitted.push(v));

    cmp.markDirty();
    expect(emitted).toEqual([true]);

    cmp.saveNotifPrefs();
    const req = httpMock.expectOne('/api/settings/notifications/');
    req.flush(DEFAULT_PREFS);

    expect(emitted).toEqual([true, false]);
  });
});
