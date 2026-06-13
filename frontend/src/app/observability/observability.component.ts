import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';

import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, interval, of, startWith, switchMap } from 'rxjs';

import { ServiceCardComponent } from '../diagnostics/service-card/service-card.component';
import { ServiceStatus } from '../diagnostics/diagnostics.service';
import { PeHelperDirective } from '../shared/directives/pe-helper.directive';
import { ObservabilityService } from './observability.service';

@Component({
  selector: 'app-observability',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ServiceCardComponent, PeHelperDirective],
  templateUrl: './observability.component.html',
  styleUrls: ['./observability.component.scss'],
})
export class ObservabilityComponent implements OnInit {
  readonly services = signal<ServiceStatus[]>([]);
  readonly error = signal<string | null>(null);

  private readonly observability = inject(ObservabilityService);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    interval(15_000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.observability.stack().pipe(
            catchError((err) => {
              this.error.set(err instanceof Error ? err.message : 'Could not refresh stack health.');
              return of({ services: [] });
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        this.services.set(res.services);
        if (res.services.length) this.error.set(null);
      });
  }

  openDashboard(service: ServiceStatus): void {
    const uid = String(service.metadata?.['dashboard_uid'] ?? 'xf-system-health');
    window.open(`http://localhost:3000/d/${uid}`, '_blank', 'noopener,noreferrer');
  }

  cardId(service: ServiceStatus): string {
    return `observability-${service.service_name.toLowerCase().replace(/\s+/g, '-')}`;
  }

  storageUsedPercent(service: ServiceStatus): number {
    const rawValue = service.metadata?.['storage_used_percent'] ?? service.metadata?.['storage_percent'] ?? 0;
    const numericValue = Number(rawValue);
    if (!Number.isFinite(numericValue)) return 0;
    return Math.min(100, Math.max(0, numericValue));
  }
}
