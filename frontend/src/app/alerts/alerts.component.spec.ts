import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of, throwError } from 'rxjs';

import { AlertsComponent } from './alerts.component';
import { NotificationService, OperatorAlert } from '../core/services/notification.service';

function alert(over: Partial<OperatorAlert> = {}): OperatorAlert {
  return {
    id: 1,
    alert_id: 'a1',
    event_type: 'disk.low',
    source_area: 'system',
    severity: 'warning',
    status: 'unread',
    title: 'Disk almost full',
    message: 'Only 5% free space.',
    dedupe_key: 'disk-low',
    occurrence_count: 1,
    related_object_type: '',
    related_object_id: '',
    related_route: '/health',
    payload: {},
    error_log_id: null,
    first_seen_at: '2026-05-09T10:00:00Z',
    last_seen_at: '2026-05-10T10:00:00Z',
    suppressed_until: null,
    read_at: null,
    acknowledged_at: null,
    resolved_at: null,
    created_at: '2026-05-09T10:00:00Z',
    updated_at: '2026-05-10T10:00:00Z',
    ...over,
  };
}

describe('AlertsComponent', () => {
  let fixture: ComponentFixture<AlertsComponent>;
  let component: AlertsComponent;
  let notifSvc: jasmine.SpyObj<NotificationService>;

  beforeEach(async () => {
    notifSvc = jasmine.createSpyObj<NotificationService>('NotificationService', [
      'loadAlerts',
      'acknowledgeAll',
      'markRead',
      'acknowledge',
      'resolve',
    ]);
    notifSvc.loadAlerts.and.returnValue(of({ count: 1, next: null, previous: null, results: [alert()] }));
    notifSvc.acknowledgeAll.and.returnValue(of({ acknowledged: 0 }));
    notifSvc.markRead.and.returnValue(of(alert()));
    notifSvc.acknowledge.and.returnValue(of(alert()));
    notifSvc.resolve.and.returnValue(of(alert()));

    await TestBed.configureTestingModule({
      imports: [AlertsComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: NotificationService, useValue: notifSvc },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AlertsComponent);
    component = fixture.componentInstance;
  });

  it('renders and loads alerts on init', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(notifSvc.loadAlerts).toHaveBeenCalled();
    expect(component.alerts().length).toBe(1);
  });

  it('onFilterChange resets page to 1 and re-fetches', () => {
    fixture.detectChanges();
    component.page.set(7);
    notifSvc.loadAlerts.calls.reset();
    component.filterStatus = 'unread';
    component.onFilterChange();
    expect(component.page()).toBe(1);
    expect(notifSvc.loadAlerts).toHaveBeenCalledWith(jasmine.objectContaining({ status: 'unread' }));
  });

  it('openRelated marks the alert read and navigates', () => {
    fixture.detectChanges();
    const router = TestBed.inject(Router);
    spyOn(router, 'navigateByUrl');
    component.openRelated(alert({ related_route: '/health' }));
    expect(notifSvc.markRead).toHaveBeenCalledWith('a1');
    expect(router.navigateByUrl).toHaveBeenCalledWith('/health');
  });

  it('handles loadAlerts error path without crashing', () => {
    notifSvc.loadAlerts.and.returnValue(throwError(() => new Error('500')));
    fixture.detectChanges();
    expect(component.loading()).toBeFalse();
  });

  it('groupAlerts dedupes by dedupe_key', () => {
    fixture.detectChanges();
    const groups = component.groupAlerts([
      alert({ alert_id: 'a1', dedupe_key: 'k1' }),
      alert({ alert_id: 'a2', dedupe_key: 'k1' }),
      alert({ alert_id: 'a3', dedupe_key: 'k2' }),
    ]);
    expect(groups.length).toBe(2);
    const k1 = groups.find((g) => g.dedupe_key === 'k1');
    expect(k1?.allIds.length).toBe(2);
  });
});
