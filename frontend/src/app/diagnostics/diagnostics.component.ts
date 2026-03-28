import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiagnosticsService, ServiceStatus, SystemConflict, FeatureReadiness, ResourceUsage } from './diagnostics.service';
import { ServiceCardComponent } from './service-card/service-card.component';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { forkJoin, Subject, takeUntil } from 'rxjs';

@Component({
  selector: 'app-diagnostics',
  standalone: true,
  imports: [
    CommonModule,
    ServiceCardComponent,
    ConflictListComponent,
    ReadinessMatrixComponent
  ],
  templateUrl: './diagnostics.component.html',
  styleUrls: ['./diagnostics.component.scss']
})
export class DiagnosticsComponent implements OnInit, OnDestroy {
  private diagnosticsService = inject(DiagnosticsService);
  private destroy$ = new Subject<void>();

  services: ServiceStatus[] = [];
  conflicts: SystemConflict[] = [];
  features: FeatureReadiness[] = [];
  resources: ResourceUsage | null = null;
  loading = true;
  refreshing = false;

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.loading = true;
    forkJoin({
      services: this.diagnosticsService.getServices(),
      conflicts: this.diagnosticsService.getConflicts(),
      features: this.diagnosticsService.getFeatures(),
      resources: this.diagnosticsService.getResources()
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: (data) => {
        this.services = data.services;
        this.conflicts = data.conflicts;
        this.features = data.features;
        this.resources = data.resources;
        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading diagnostics data', err);
        this.loading = false;
      }
    });
  }

  refreshAll(): void {
    this.refreshing = true;
    forkJoin({
      services: this.diagnosticsService.refreshServices(),
      conflicts: this.diagnosticsService.detectConflicts()
    }).pipe(takeUntil(this.destroy$)).subscribe({
      next: () => {
        this.loadData();
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Error refreshing diagnostics', err);
        this.refreshing = false;
      }
    });
  }

  onResolveConflict(id: number): void {
    this.diagnosticsService.resolveConflict(id).pipe(takeUntil(this.destroy$)).subscribe(() => {
      this.conflicts = this.conflicts.filter(c => c.id !== id);
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  getHealthyCount(): number {
    return this.services.filter(s => s.state === 'healthy').length;
  }
}
