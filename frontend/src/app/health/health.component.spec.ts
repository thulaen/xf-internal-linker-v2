import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { EMPTY, of, Subject } from 'rxjs';

import { HealthComponent } from './health.component';
import { HealthService, ServiceHealth } from './health.service';
import { SyncService } from '../jobs/sync.service';
import { VisibilityGateService } from '../core/util/visibility-gate.service';

function svc(key: string, status: ServiceHealth['status'] = 'healthy'): ServiceHealth {
  return {
    service_key: key,
    service_name: key,
    service_description: '',
    status,
    status_label: status,
    config_tier: 'optional',
    last_check_at: '2026-05-10T00:00:00Z',
    last_success_at: null,
    last_error_at: null,
    last_error_message: '',
    issue_description: '',
    suggested_fix: '',
    metadata: {},
  } as ServiceHealth;
}

describe('HealthComponent', () => {
  let fixture: ComponentFixture<HealthComponent>;
  let component: HealthComponent;
  let healthSvc: jasmine.SpyObj<HealthService>;

  beforeEach(async () => {
    healthSvc = jasmine.createSpyObj<HealthService>('HealthService', [
      'getHealthStatus',
      'getSummary',
      'getDiskHealth',
      'getGpuHealth',
      'checkAll',
      'checkService',
    ]);
    healthSvc.getHealthStatus.and.returnValue(of([svc('database'), svc('redis', 'warning')]));
    healthSvc.getSummary.and.returnValue(of({
      system_status: 'healthy', total_services: 2, degraded_count: 1, last_check_at: null,
    }));
    healthSvc.getDiskHealth.and.returnValue(of({
      db_size_mb: 1, embeddings_size_mb: 1, items_count: 0,
    }));
    healthSvc.getGpuHealth.and.returnValue(of({
      temp_c: null, vram_total_mb: null, vram_used_mb: null, utilization_pct: null, available: false,
    }));
    healthSvc.checkAll.and.returnValue(of({}));
    healthSvc.checkService.and.returnValue(of(svc('database')));

    // The real template uses 14 `i18n=` markers; the test polyfills do not
    // load `@angular/localize/init`, so a real render throws
    // "$localize is not defined". Stub the template — the spec's job is
    // to exercise the TS class (signals, service wiring, error paths).
    TestBed.overrideComponent(HealthComponent, {
      set: { template: '<div data-test="health-stub"></div>', imports: [], styles: [] },
    });

    await TestBed.configureTestingModule({
      imports: [HealthComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        provideNoopAnimations(),
        { provide: HealthService, useValue: healthSvc },
        { provide: SyncService, useValue: { getJobs: () => of([]) } },
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(HealthComponent);
    component = fixture.componentInstance;
  });

  it('renders without throwing and loads service list on init', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(healthSvc.getHealthStatus).toHaveBeenCalled();
    expect(component.services().length).toBe(2);
  });

  it('refreshAll re-fetches services after checkAll completes', () => {
    fixture.detectChanges();
    healthSvc.getHealthStatus.calls.reset();
    component.refreshAll();
    expect(healthSvc.checkAll).toHaveBeenCalled();
    expect(healthSvc.getHealthStatus).toHaveBeenCalled();
  });

  it('keeps loading=false and logs error when getHealthStatus fails', () => {
    const errorSubject = new Subject<ServiceHealth[]>();
    healthSvc.getHealthStatus.and.returnValue(errorSubject.asObservable());
    spyOn(console, 'error');
    fixture.detectChanges();
    errorSubject.error(new Error('boom'));
    expect(component.loading()).toBeFalse();
    expect(console.error).toHaveBeenCalled();
  });

  it('refreshService updates the matching service in the list', () => {
    fixture.detectChanges();
    const updated = svc('database', 'error');
    healthSvc.checkService.and.returnValue(of(updated));
    component.refreshService('database');
    const dbAfter = component.services().find((s) => s.service_key === 'database');
    expect(dbAfter?.status).toBe('error');
  });
});
