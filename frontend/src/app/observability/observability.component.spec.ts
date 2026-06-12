import { TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Observable, Subject, of, throwError } from 'rxjs';

import { ServiceStatus } from '../diagnostics/diagnostics.service';
import { ObservabilityComponent } from './observability.component';
import { ObservabilityService } from './observability.service';

describe('ObservabilityComponent', () => {
  const makeService = (overrides: Partial<ServiceStatus>): ServiceStatus => ({
    id: 1,
    service_name: 'VictoriaMetrics',
    state: 'healthy',
    explanation: 'Connected',
    last_check: '2026-05-21T09:00:00Z',
    last_success: '2026-05-21T09:00:00Z',
    last_failure: null,
    next_action_step: 'No action needed.',
    metadata: {},
    ...overrides,
  });

  function configureComponent(response: Observable<{ services: ServiceStatus[] }>): void {
    TestBed.configureTestingModule({
      imports: [ObservabilityComponent, NoopAnimationsModule],
      providers: [
        {
          provide: ObservabilityService,
          useValue: {
            stack: vi.fn().mockReturnValue(response),
          },
        },
      ],
    });
  }

  // TODO(AutoIssue #21241): Given a list of services, When rendered, Then each card button has an aria-label with the service name.
  it('renders one card per observability service and opens the configured dashboard', fakeAsync(() => {
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(undefined as never);
    configureComponent(of({
      services: [
      makeService({
        service_name: 'VictoriaMetrics',
        metadata: { dashboard_uid: 'xf-system-health', storage_used_percent: 64 },
      }),
      makeService({
        id: 2,
        service_name: 'Grafana',
        metadata: { dashboard_uid: 'xf-import' },
      }),
    ],
    }));
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const page = fixture.nativeElement.querySelector('#observability-page');
    const grid = fixture.nativeElement.querySelector('.service-grid');
    const cards = fixture.nativeElement.querySelectorAll('.stack-card');
    expect(page).toBeTruthy();
    expect(grid).toBeTruthy();
    expect(cards.length).toBe(2);
    expect(fixture.nativeElement.querySelector('#observability-victoriametrics')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Grafana');

    const progress = fixture.nativeElement.querySelector('[data-storage-used-percent]');
    expect(progress?.getAttribute('data-storage-used-percent')).toBe('64');

    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(button.getAttribute('aria-label')).toBe('Open VictoriaMetrics dashboard');
    button.click();
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:3000/d/xf-system-health',
      '_blank',
      'noopener,noreferrer',
    );
    fixture.destroy();
    discardPeriodicTasks();
  }));

  // TODO(AutoIssue #21243): Given the observability component is destroyed, When time passes, Then it stops polling the interval.
  it('releases the polling interval when the component is destroyed', fakeAsync(() => {
    const stackSubject = new Subject<{ services: ServiceStatus[] }>();
    configureComponent(stackSubject.asObservable());
    const fixture = TestBed.createComponent(ObservabilityComponent);
    const service = TestBed.inject(ObservabilityService);
    
    fixture.detectChanges(); // Trigger ngOnInit
    expect(service.stack).toHaveBeenCalledTimes(1);
    
    tick(15000);
    expect(service.stack).toHaveBeenCalledTimes(2);
    
    fixture.destroy(); // Trigger destroy
    tick(30000);
    expect(service.stack).toHaveBeenCalledTimes(2); // Should not increase
    
    discardPeriodicTasks();
  }));

  it('shows a plain error notice when stack health cannot refresh', fakeAsync(() => {
    configureComponent(throwError(() => new Error('Stack health is unavailable.')));
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const notice = fixture.nativeElement.querySelector('.notice-card');
    expect(notice?.textContent).toContain('Stack health is unavailable.');
    expect(fixture.nativeElement.querySelectorAll('.stack-card').length).toBe(0);

    fixture.destroy();
    discardPeriodicTasks();
  }));

  // TODO(AutoIssue #21245): Given a successful empty response, When loaded, Then it shows a loading/empty state.
  it('handles empty service list gracefully', fakeAsync(() => {
    configureComponent(of({ services: [] }));
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const loading = fixture.nativeElement.querySelector('.loading-row');
    expect(loading).toBeTruthy();
    expect(loading.textContent).toContain('Loading stack health...');
    expect(fixture.nativeElement.querySelectorAll('.stack-card').length).toBe(0);

    fixture.destroy();
    discardPeriodicTasks();
  }));

  it('clamps storage percentages and builds stable card ids', () => {
    configureComponent(of({ services: [] }));
    const fixture = TestBed.createComponent(ObservabilityComponent);
    const component = fixture.componentInstance;

    expect(component.cardId(makeService({ service_name: 'OTel Collector' }))).toBe(
      'observability-otel-collector',
    );
    expect(
      component.storageUsedPercent(makeService({ metadata: { storage_used_percent: '150' } })),
    ).toBe(100);
    expect(
      component.storageUsedPercent(makeService({ metadata: { storage_percent: '-4' } })),
    ).toBe(0);
    expect(
      component.storageUsedPercent(makeService({ metadata: { storage_used_percent: 'missing' } })),
    ).toBe(0);

    fixture.destroy();
  });
});


