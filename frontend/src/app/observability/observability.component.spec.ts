import { TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

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

  function configureComponent(services: ServiceStatus[]): void {
    TestBed.configureTestingModule({
      imports: [ObservabilityComponent, NoopAnimationsModule],
      providers: [
        {
          provide: ObservabilityService,
          useValue: {
            stack: jasmine.createSpy('stack').and.returnValue(of({ services })),
          },
        },
      ],
    });
  }

  it('renders one card per observability service and opens the configured dashboard', fakeAsync(() => {
    const openSpy = spyOn(window, 'open');
    configureComponent([
      makeService({
        service_name: 'VictoriaMetrics',
        metadata: { dashboard_uid: 'xf-system-health', storage_used_percent: 64 },
      }),
      makeService({
        id: 2,
        service_name: 'Grafana',
        metadata: { dashboard_uid: 'xf-import' },
      }),
    ]);
    const fixture = TestBed.createComponent(ObservabilityComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    const cards = fixture.nativeElement.querySelectorAll('.stack-card');
    expect(cards.length).toBe(2);
    expect(fixture.nativeElement.querySelector('#observability-victoriametrics')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Grafana');

    const progress = fixture.nativeElement.querySelector('mat-progress-bar');
    expect(progress?.getAttribute('data-storage-used-percent')).toBe('64');

    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click();
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:3000/d/xf-system-health',
      '_blank',
      'noopener,noreferrer',
    );
    fixture.destroy();
    discardPeriodicTasks();
  }));
});
