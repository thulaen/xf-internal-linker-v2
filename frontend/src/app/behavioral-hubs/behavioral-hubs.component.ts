import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
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
import { timer } from 'rxjs';
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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BehavioralHubsComponent implements OnInit {
  private svc = inject(BehavioralHubService);
  // Phase E2 / Gap 41 — cancel in-flight HTTP on route leave.
  private destroyRef = inject(DestroyRef);

  // Hub list state
  readonly hubs = signal<BehavioralHub[]>([]);
  readonly totalHubs = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(25);
  readonly loadingHubs = signal(false);

  readonly hubColumns: readonly string[] = ['name', 'member_count', 'auto_link_enabled', 'detection_method', 'updated_at', 'actions'];

  // Hub detail state
  readonly selectedHub = signal<BehavioralHubDetail | null>(null);
  readonly loadingDetail = signal(false);
  /** ngModel two-way — needs an lvalue, stays plain. (ngModelChange) fires
   *  on the host so OnPush sees CD per keystroke. */
  editName = '';
  readonly savingName = signal(false);
  readonly togglingAutoLink = signal(false);

  // Run stats
  readonly lastRun = signal<SessionCoOccurrenceRun | null>(null);
  readonly loadingRuns = signal(false);
  readonly triggeringCompute = signal(false);
  readonly triggeringDetect = signal(false);

  // Settings (for stats display)
  readonly settings = signal<CoOccurrenceSettings | null>(null);

  ngOnInit(): void {
    this.loadHubs();
    this.loadRuns();
    this.loadSettings();
  }

  loadHubs(): void {
    this.loadingHubs.set(true);
    this.svc.getHubs(this.page(), this.pageSize())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.hubs.set(res.results);
          this.totalHubs.set(res.count);
          this.loadingHubs.set(false);
        },
        error: (err) => {
          this.loadingHubs.set(false);
          console.error('behavioral-hubs getHubs error', err);
        },
      });
  }

  loadRuns(): void {
    this.loadingRuns.set(true);
    this.svc.getRuns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (runs) => {
          this.lastRun.set(runs.length > 0 ? runs[0] : null);
          this.loadingRuns.set(false);
        },
        error: (err) => {
          this.loadingRuns.set(false);
          console.error('behavioral-hubs getRuns error', err);
        },
      });
  }

  loadSettings(): void {
    this.svc.getSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => this.settings.set(s),
        error: (err) => console.error('behavioral-hubs getSettings error', err),
      });
  }

  onPageChange(event: PageEvent): void {
    this.page.set(event.pageIndex + 1);
    this.pageSize.set(event.pageSize);
    this.loadHubs();
  }

  openHub(hub: BehavioralHub): void {
    this.loadingDetail.set(true);
    this.selectedHub.set(null);
    this.svc.getHub(hub.hub_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (detail) => {
          this.selectedHub.set(detail);
          this.editName = detail.name;
          this.loadingDetail.set(false);
        },
        error: (err) => {
          this.loadingDetail.set(false);
          console.error('behavioral-hubs getHub error', err);
        },
      });
  }

  closeDetail(): void {
    this.selectedHub.set(null);
    this.editName = '';
  }

  saveName(): void {
    const current = this.selectedHub();
    if (!current || !this.editName.trim()) return;
    this.savingName.set(true);
    this.svc.patchHub(current.hub_id, { name: this.editName.trim() })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          // Atomic update — replace the captured snapshot field. Read-time
          // re-check keeps the patch correct even if the user navigated
          // through hubs while the request was in flight (no clobbering
          // the wrong hub's name).
          this.selectedHub.update((curr) =>
            curr && curr.hub_id === current.hub_id
              ? { ...curr, name: updated.name }
              : curr,
          );
          this.savingName.set(false);
          this.loadHubs();
        },
        error: (err) => {
          this.savingName.set(false);
          console.error('behavioral-hubs saveName error', err);
        },
      });
  }

  toggleAutoLink(): void {
    const current = this.selectedHub();
    if (!current) return;
    this.togglingAutoLink.set(true);
    this.svc
      .patchHub(current.hub_id, { auto_link_enabled: !current.auto_link_enabled })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.selectedHub.update((curr) =>
            curr && curr.hub_id === current.hub_id
              ? { ...curr, auto_link_enabled: updated.auto_link_enabled }
              : curr,
          );
          this.togglingAutoLink.set(false);
          this.loadHubs();
        },
        error: (err) => {
          this.togglingAutoLink.set(false);
          console.error('behavioral-hubs toggleAutoLink error', err);
        },
      });
  }

  removeMember(member: BehavioralHubMembership): void {
    const current = this.selectedHub();
    if (!current) return;
    this.svc.removeMember(current.hub_id, member.content_item_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Atomic single-update: filter the member out and recompute
          // the displayed count in one go. Previously did two separate
          // mutations (members assignment + member_count assignment) —
          // under signals that's two writes that could observe stale
          // intermediate state.
          this.selectedHub.update((curr) => {
            if (!curr || curr.hub_id !== current.hub_id) return curr;
            const members = curr.members.filter((m) => m.id !== member.id);
            const member_count = members.filter(
              (m) => m.membership_source !== 'manual_remove_override',
            ).length;
            return { ...curr, members, member_count };
          });
        },
        error: (err) => {
          console.error('Failed to remove hub member', err);
          // Re-fetch to get authoritative state. Guard against the user
          // having closed the detail panel mid-flight (selectedHub may
          // now be null).
          const hub = this.selectedHub();
          if (hub && hub.hub_id === current.hub_id) {
            this.openHub(hub);
          }
        },
      });
  }

  triggerCompute(): void {
    this.triggeringCompute.set(true);
    this.svc.triggerCompute()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.triggeringCompute.set(false);
          this.loadRuns();
        },
        error: (err) => {
          this.triggeringCompute.set(false);
          console.error('behavioral-hubs triggerCompute error', err);
        },
      });
  }

  triggerDetect(): void {
    this.triggeringDetect.set(true);
    this.svc.triggerDetection()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.triggeringDetect.set(false);
          // Wait for the worker to finish before re-fetching. timer +
          // takeUntilDestroyed correctly cancels on route navigation —
          // the previous bare setTimeout kept firing 2s after the user
          // had left the page (and `detectTimeout` field + manual
          // clearTimeout in ngOnDestroy is no longer needed).
          timer(2000)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe(() => this.loadHubs());
        },
        error: (err) => {
          this.triggeringDetect.set(false);
          console.error('behavioral-hubs triggerDetect error', err);
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
