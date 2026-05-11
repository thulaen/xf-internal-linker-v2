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

  it('computes healthyCount from services signal', () => {
    fixture.detectChanges();
    expect(component.healthyCount()).toBe(1);
    expect(component.warningCount()).toBe(1);
  });

  it('computes errorCount when services have error status', () => {
    fixture.detectChanges();
    component.services.set([svc('db1', 'error'), svc('db2', 'down')]);
    expect(component.errorCount()).toBe(2);
  });

  it('getStatusIcon returns correct icon for each status', () => {
    expect(component.getStatusIcon('healthy')).toBe('check_circle');
    expect(component.getStatusIcon('error')).toBe('error');
    expect(component.getStatusIcon('down')).toBe('dangerous');
    expect(component.getStatusIcon('warning')).toBe('warning');
    expect(component.getStatusIcon('stale')).toBe('update');
  });

  it('getStatusClass returns status-prefixed class', () => {
    expect(component.getStatusClass('healthy')).toBe('status-healthy');
    expect(component.getStatusClass('error')).toBe('status-error');
  });

  it('getServiceName uses service_name or derives from service_key', () => {
    const s1 = svc('my_service');
    const s2 = { ...svc('my_service'), service_name: 'Custom Name' };
    expect(component.getServiceName(s1)).toBe('my_service');
    expect(component.getServiceName(s2 as ServiceHealth)).toBe('Custom Name');
  });

  it('getServiceDescription returns description or empty string', () => {
    const s1 = svc('my_service');
    const s2 = { ...svc('my_service'), service_description: 'Test description' };
    expect(component.getServiceDescription(s1)).toBe('');
    expect(component.getServiceDescription(s2 as ServiceHealth)).toBe('Test description');
  });

  it('refreshService sets and clears refreshingServices flag', () => {
    fixture.detectChanges();
    // Override the spy to return a subject we can control
    const checkServiceSubject = new Subject<ServiceHealth>();
    healthSvc.checkService.and.returnValue(checkServiceSubject.asObservable());

    expect(component.refreshingServices().has('database')).toBeFalse();
    component.refreshService('database');
    // Flag is set synchronously before the observable completes
    expect(component.refreshingServices().has('database')).toBeTrue();

    // Emit the result to complete the observable
    checkServiceSubject.next(svc('database'));
    checkServiceSubject.complete();
    // Flag is cleared after finalize runs
    expect(component.refreshingServices().has('database')).toBeFalse();
  });

  it('tracks job by id', () => {
    const job = { job_id: '123', status: 'running' };
    expect(component.trackJobId(0, job as any)).toBe('123');
  });

  it('getSettingsFragment maps service keys to fragment identifiers', () => {
    expect(component.getSettingsFragment('ga4')).toBe('ga4-settings');
    expect(component.getSettingsFragment('matomo')).toBe('matomo-settings');
    expect(component.getSettingsFragment('model_runtime')).toBe('model-runtime');
    expect(component.getSettingsFragment('unknown')).toBeUndefined();
  });

  it('getInfraFixHint provides actionable hints for infrastructure services', () => {
    const dbHint = component.getInfraFixHint('database');
    expect(dbHint).toContain('PostgreSQL');
    const redisHint = component.getInfraFixHint('redis');
    expect(redisHint).toContain('Redis');
  });
});
