import { Component, DestroyRef, OnInit, OnDestroy, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  BehavioralHub,
  BehavioralHubDetail,
  BehavioralHubMembership,
  BehavioralHubService,
  CoOccurrenceSettings,
  SessionCoOccurrenceRun,
} from './behavioral-hub.service';

@Component({
  selector: 'app-behavioral-hubs',
  standalone: true,
  imports: [
    CommonModule,
    DatePipe,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatTooltipModule,
  ],
  templateUrl: './behavioral-hubs.component.html',
  styleUrls: ['./behavioral-hubs.component.scss'],
})
export class BehavioralHubsComponent implements OnInit, OnDestroy {
  private svc = inject(BehavioralHubService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);
  private detectTimeout: ReturnType<typeof setTimeout> | null = null;

  // Hub list state
  hubs: BehavioralHub[] = [];
  totalHubs = 0;
  page = 1;
  pageSize = 25;
  loadingHubs = false;

  hubColumns = ['name', 'member_count', 'auto_link_enabled', 'detection_method', 'updated_at', 'actions'];

  // Hub detail state
  selectedHub: BehavioralHubDetail | null = null;
  loadingDetail = false;
  editName = '';
  savingName = false;
  togglingAutoLink = false;

  // Run stats
  lastRun: SessionCoOccurrenceRun | null = null;
  loadingRuns = false;
  triggeringCompute = false;
  triggeringDetect = false;

  // Settings (for stats display)
  settings: CoOccurrenceSettings | null = null;

  ngOnInit(): void {
    this.loadHubs();
    this.loadRuns();
    this.loadSettings();
  }

  ngOnDestroy(): void {
    if (this.detectTimeout) {
      clearTimeout(this.detectTimeout);
    }
  }

  loadHubs(): void {
    this.loadingHubs = true;
    this.svc.getHubs(this.page, this.pageSize)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (res) => {
        this.hubs = res.results;
        this.totalHubs = res.count;
        this.loadingHubs = false;
      },
      error: () => {
        this.loadingHubs = false;
      },
    });
  }

  loadRuns(): void {
    this.loadingRuns = true;
    this.svc.getRuns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (runs) => {
        this.lastRun = runs.length > 0 ? runs[0] : null;
        this.loadingRuns = false;
      },
      error: () => {
        this.loadingRuns = false;
      },
    });
  }

  loadSettings(): void {
    this.svc.getSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (s) => (this.settings = s),
      error: () => {},
    });
  }

  onPageChange(event: PageEvent): void {
    this.page = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadHubs();
  }

  openHub(hub: BehavioralHub): void {
    this.loadingDetail = true;
    this.selectedHub = null;
    this.svc.getHub(hub.hub_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (detail) => {
        this.selectedHub = detail;
        this.editName = detail.name;
        this.loadingDetail = false;
      },
      error: () => {
        this.loadingDetail = false;
      },
    });
  }

  closeDetail(): void {
    this.selectedHub = null;
    this.editName = '';
  }

  saveName(): void {
    if (!this.selectedHub || !this.editName.trim()) return;
    this.savingName = true;
    this.svc.patchHub(this.selectedHub.hub_id, { name: this.editName.trim() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: (updated) => {
        if (this.selectedHub) this.selectedHub.name = updated.name;
        this.savingName = false;
        this.loadHubs();
      },
      error: () => {
        this.savingName = false;
      },
    });
  }

  toggleAutoLink(): void {
    if (!this.selectedHub) return;
    this.togglingAutoLink = true;
    this.svc
      .patchHub(this.selectedHub.hub_id, { auto_link_enabled: !this.selectedHub.auto_link_enabled })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          if (this.selectedHub) this.selectedHub.auto_link_enabled = updated.auto_link_enabled;
          this.togglingAutoLink = false;
          this.loadHubs();
        },
        error: () => {
          this.togglingAutoLink = false;
        },
      });
  }

  removeMember(member: BehavioralHubMembership): void {
    if (!this.selectedHub) return;
    this.svc.removeMember(this.selectedHub.hub_id, member.content_item_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        if (this.selectedHub) {
          this.selectedHub.members = this.selectedHub.members.filter(
            (m) => m.id !== member.id
          );
          this.selectedHub.member_count = this.selectedHub.members.filter(
            (m) => m.membership_source !== 'manual_remove_override'
          ).length;
        }
      },
      error: (err) => { console.error('Failed to remove hub member', err); this.openHub(this.selectedHub!); },
    });
  }

  triggerCompute(): void {
    this.triggeringCompute = true;
    this.svc.triggerCompute()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.triggeringCompute = false;
        this.loadRuns();
      },
      error: () => {
        this.triggeringCompute = false;
      },
    });
  }

  triggerDetect(): void {
    this.triggeringDetect = true;
    this.svc.triggerDetection()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.triggeringDetect = false;
        this.detectTimeout = setTimeout(() => this.loadHubs(), 2000);
      },
      error: () => {
        this.triggeringDetect = false;
      },
    });
  }

  membershipLabel(source: string): string {
    const map: Record<string, string> = {
      auto_detected: 'Auto',
      manual_add: 'Manual',
      manual_remove_override: 'Removed',
    };
    return map[source] ?? source;
  }
}
