import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subject, takeUntil } from 'rxjs';
import { DiagnosticsService, MetaTournamentResponse, TournamentPromotion, TournamentSlot } from '../diagnostics.service';

@Component({
  selector: 'app-meta-tournament',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    MatChipsModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './meta-tournament.component.html',
  styleUrls: ['./meta-tournament.component.scss'],
})
export class MetaTournamentComponent implements OnInit, OnDestroy {
  private diagnosticsService = inject(DiagnosticsService);
  private destroy$ = new Subject<void>();

  data: MetaTournamentResponse | null = null;
  loading = true;
  running = false;
  expandedSlot: string | null = null;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.diagnosticsService
      .getMetaTournament()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (d) => {
          this.data = d;
          this.loading = false;
        },
        error: () => {
          this.loading = false;
        },
      });
  }

  runAll(): void {
    this.running = true;
    this.diagnosticsService
      .triggerMetaTournament()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: () => {
          this.running = false;
        },
        error: () => {
          this.running = false;
        },
      });
  }

  runSlot(slotId: string): void {
    this.diagnosticsService
      .triggerMetaTournament(slotId)
      .pipe(takeUntil(this.destroy$))
      .subscribe();
  }

  togglePin(slot: TournamentSlot): void {
    this.diagnosticsService
      .pinMetaTournamentSlot(slot.slot_id, !slot.pinned)
      .pipe(takeUntil(this.destroy$))
      .subscribe((result) => {
        slot.pinned = result.pinned;
      });
  }

  toggleExpand(slotId: string): void {
    this.expandedSlot = this.expandedSlot === slotId ? null : slotId;
  }

  trackBySlotId(_: number, slot: TournamentSlot): string {
    return slot.slot_id;
  }

  trackByPromotion(_: number, p: TournamentPromotion): string {
    return `${p.evaluated_at}:${p.meta_id}`;
  }

  formatNdcg(value: number | null | undefined): string {
    if (value == null) return '—';
    return (value * 100).toFixed(2) + '%';
  }

  formatDelta(value: number | null | undefined): string {
    if (value == null) return '—';
    const sign = value >= 0 ? '+' : '';
    return sign + (value * 100).toFixed(2) + '%';
  }

  deltaClass(value: number | null | undefined): string {
    if (value == null) return '';
    return value >= 0 ? 'delta-positive' : 'delta-negative';
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
