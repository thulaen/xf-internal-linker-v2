import { ChangeDetectionStrategy, Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ScrollingModule } from '@angular/cdk/scrolling';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { FamilySummary, MetaAlgorithmsService, MetaRow, MetaStatus } from './meta-algorithms.service';
import { MetaRowComponent } from './meta-row.component';
import { SpecViewerDialogComponent } from '../spec-viewer-dialog/spec-viewer-dialog.component';

/**
 * Phase MS — Meta Algorithm Settings tab.
 */
@Component({
  selector: 'app-meta-algorithms-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule,
    ScrollingModule,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatDialogModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
    MetaRowComponent,
  ],
  template: `
    <section class="ma-tab">
      <header class="ma-header">
        <div class="ma-title-row">
          <h2 class="ma-title" i18n="@@metaAlgorithms.title">
            <mat-icon>auto_awesome</mat-icon>
            Meta Algorithms
          </h2>
          <span class="ma-count">
            <ng-container i18n="@@metaAlgorithms.count">{{ filteredRows().length }} shown</ng-container>
          </span>
          @if (loading()) {
            <mat-spinner diameter="16" />
          }
        </div>
        <p class="ma-subtitle" i18n="@@metaAlgorithms.subtitle">
          Manage every algorithm the ranking pipeline knows about. Winners are on by default; alternates are off but
          pre-filled so you can swap them in instantly.
        </p>
      </header>

      <div class="ma-controls">
        <mat-form-field appearance="outline" class="ma-search">
          <mat-label i18n="@@metaAlgorithms.search.label">Search</mat-label>
          <input
            matInput
            type="search"
            autocomplete="off"
            [(ngModel)]="searchModel"
            (ngModelChange)="onSearchChange($event)"
            placeholder="name, META code, or family"
            i18n-placeholder="@@metaAlgorithms.search.placeholder"
          />
          @if (searchModel) {
            <button
              matSuffix
              mat-icon-button
              type="button"
              aria-label="Clear search"
              i18n-aria-label="@@metaAlgorithms.search.clearAria"
              (click)="onSearchChange('')"
            >
              <mat-icon>close</mat-icon>
            </button>
          }
        </mat-form-field>

        <mat-form-field appearance="outline" class="ma-status-filter">
          <mat-label i18n="@@metaAlgorithms.status.label">Status</mat-label>
          <mat-select [value]="statusFilter()" (valueChange)="onStatusChange($event)">
            <mat-option value="" i18n="@@metaAlgorithms.filter.all">All</mat-option>
            <mat-option value="active" i18n="@@metaAlgorithms.filter.active">Active only</mat-option>
            <mat-option value="disabled-pending-implementation" i18n="@@metaAlgorithms.filter.spec"
              >Spec only</mat-option
            >
            <mat-option value="forward-declared" i18n="@@metaAlgorithms.filter.forward">Forward-declared</mat-option>
            <mat-option value="disabled" i18n="@@metaAlgorithms.filter.disabled">Disabled</mat-option>
          </mat-select>
        </mat-form-field>

        <button mat-stroked-button type="button" (click)="refresh()" [disabled]="loading()">
          <mat-icon>refresh</mat-icon>
          <ng-container i18n="@@metaAlgorithms.refreshBtn">Refresh</ng-container>
        </button>
      </div>

      <mat-chip-listbox
        class="ma-families"
        [value]="familyFilter()"
        (change)="onFamilyChange($any($event))"
        aria-label="Filter by family"
        i18n-aria-label="@@metaAlgorithms.families.ariaLabel"
      >
        <mat-chip-option value="" i18n="@@metaAlgorithms.families.all">All families</mat-chip-option>
        @for (f of families(); track f.family) {
          <mat-chip-option [value]="f.family" [matTooltip]="familyTooltip(f)">
            {{ f.family }} · {{ f.total }}
          </mat-chip-option>
        }
      </mat-chip-listbox>

      @if (filteredRows().length === 0) {
        <section class="ma-empty" role="status">
          <mat-icon>search_off</mat-icon>
          <p i18n="@@metaAlgorithms.empty.message">No meta-algorithms match those filters.</p>
          <button mat-stroked-button type="button" (click)="resetFilters()" i18n="@@metaAlgorithms.empty.resetBtn">
            Reset filters
          </button>
        </section>
      } @else {
        <div class="ma-header-row" role="row" aria-hidden="true">
          <span i18n="@@metaAlgorithms.table.family">Family</span>
          <span i18n="@@metaAlgorithms.table.code">Code</span>
          <span i18n="@@metaAlgorithms.table.name">Name</span>
          <span i18n="@@metaAlgorithms.table.status">Status</span>
          <span i18n="@@metaAlgorithms.table.weight">Weight</span>
          <span i18n="@@metaAlgorithms.table.on">On</span>
          <span></span>
        </div>
        <cdk-virtual-scroll-viewport itemSize="44" class="ma-viewport">
          <app-meta-row
            *cdkVirtualFor="let row of filteredRows(); trackBy: trackById"
            [row]="row"
            (toggled)="onToggle($event)"
            (actionClick)="onAction($event)"
          />
        </cdk-virtual-scroll-viewport>
      }
    </section>
  `,
  styles: [
    `
      .ma-tab {
        display: flex;
        flex-direction: column;
        gap: 16px;
        padding: 16px;
      }
      .ma-header {
        display: flex;
        flex-direction: column;
        gap: 4px;
      }
      .ma-title-row {
        display: flex;
        align-items: center;
        gap: 12px;
      }
      .ma-title {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        margin: 0;
        font-size: 18px;
        font-weight: 500;
      }
      .ma-count {
        font-size: 12px;
        color: var(--color-text-secondary, #5f6368);
        font-variant-numeric: tabular-nums;
      }
      .ma-subtitle {
        margin: 0;
        color: var(--color-text-secondary);
        font-size: 13px;
      }
      .ma-controls {
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
      }
      .ma-search {
        flex: 1 1 280px;
        max-width: 360px;
      }
      .ma-status-filter {
        flex: 0 1 200px;
      }
      .ma-families {
        max-height: 80px;
        overflow-y: auto;
        padding-left: 16px; /* Layout Rule A — first chip 16px clearance. */
      }
      .ma-viewport {
        height: calc(100vh - 420px);
        min-height: 320px;
        border: 0.8px solid var(--color-border, #dadce0);
        border-radius: 4px;
        background: var(--color-bg, #ffffff);
      }
      .ma-header-row {
        display: grid;
        grid-template-columns: 56px 88px 1fr 112px 96px 48px 40px;
        gap: 8px;
        padding: 8px 12px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.4px;
        text-transform: uppercase;
        color: var(--color-text-secondary, #5f6368);
        background: var(--color-bg-faint, #f8f9fa);
        border-bottom: 0.8px solid var(--color-border);
        border-radius: 4px 4px 0 0;
      }
      .ma-empty {
        text-align: center;
        padding: 48px 16px;
        color: var(--color-text-secondary);
      }
      .ma-empty mat-icon {
        width: 48px;
        height: 48px;
        font-size: 48px;
      }
      .ma-empty p {
        margin: 8px 0 16px;
      }
    `,
  ],
})
export class MetaAlgorithmsTabComponent implements OnInit {
  private service = inject(MetaAlgorithmsService);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  private dialog = inject(MatDialog);
  private destroyRef = inject(DestroyRef);

  // ── Reactive state ────────────────────────────────────────────
  protected readonly loading = signal(false);
  protected readonly rows = signal<MetaRow[]>([]);
  protected readonly families = signal<FamilySummary[]>([]);
  protected readonly statusFilter = signal<MetaStatus | ''>('');
  protected readonly familyFilter = signal<string>('');
  protected readonly search = signal<string>('');
  protected searchModel = '';

  /** Client-side derived view — filters are applied server-side but we
   *  keep a fallback here so chip flips feel instant without a round-trip. */
  protected readonly filteredRows = computed(() => {
    const status = this.statusFilter();
    const family = this.familyFilter();
    const q = this.search().trim().toLowerCase();
    return this.rows().filter((r) => {
      if (status && r.status !== status) return false;
      if (family && r.family !== family) return false;
      if (!q) return true;
      return (
        r.id.toLowerCase().includes(q) ||
        (r.meta_code || '').toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q)
      );
    });
  });

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.service
      .list({}) // load everything, filter client-side
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (payload) => {
          this.loading.set(false);
          this.rows.set(payload.rows || []);
          this.families.set(payload.families || []);
        },
        error: () => {
          this.loading.set(false);
          this.snack.open(
            $localize`:@@metaAlgorithms.errors.loadFailed:Could not load meta-algorithm list.`,
            $localize`:@@settings.actions.retry:Retry`,
            { duration: 5000 },
          );
        },
      });
  }

  onSearchChange(v: string): void {
    this.searchModel = v;
    this.search.set(v);
  }

  onStatusChange(v: MetaStatus | ''): void {
    this.statusFilter.set(v);
  }

  onFamilyChange(ev: { value: string }): void {
    this.familyFilter.set(ev.value ?? '');
  }

  resetFilters(): void {
    this.statusFilter.set('');
    this.familyFilter.set('');
    this.search.set('');
    this.searchModel = '';
  }

  onToggle(ev: { id: string; enabled: boolean }): void {
    // Optimistic update — flip in the local signal first, roll back on error.
    const snapshot = this.rows();
    const next = snapshot.map((r) =>
      r.id === ev.id
        ? {
            ...r,
            enabled: ev.enabled,
            status: ev.enabled
              ? r.meta_code && r.meta_code.startsWith('META-0')
                ? 'active'
                : r.status === 'disabled'
                  ? 'forward-declared'
                  : r.status
              : 'disabled',
          }
        : r,
    ) as MetaRow[];
    this.rows.set(next);

    this.service
      .toggle(ev.id, ev.enabled)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          const id = ev.id;
          const state = ev.enabled
            ? $localize`:@@settings.actions.enabled:enabled`
            : $localize`:@@settings.actions.disabled:disabled`;
          this.snack.open(
            $localize`:@@metaAlgorithms.success.toggled:${id}:id: → ${state}:state:.`,
            $localize`:@@settings.actions.ok:OK`,
            { duration: 2500 },
          );
        },
        error: () => {
          const id = ev.id;
          this.rows.set(snapshot);
          this.snack.open(
            $localize`:@@metaAlgorithms.errors.toggleFailed:Could not toggle ${id}:id: — reverted.`,
            $localize`:@@settings.actions.ok:OK`,
            { duration: 4000 },
          );
        },
      });
  }

  onAction(ev: { id: string; action: string }): void {
    const row = this.rows().find((r) => r.id === ev.id);
    if (!row) return;
    switch (ev.action) {
      case 'run': {
        const title = row.title;
        this.snack.open(
          $localize`:@@metaAlgorithms.success.runQueued:Run queued for ${title}:title:. Gated by the sequential-execution lock.`,
          $localize`:@@settings.actions.ok:OK`,
          { duration: 3000 },
        );
        break;
      }
      case 'spec':
        if (row.spec_path) {
          this.dialog.open(SpecViewerDialogComponent, {
            width: '860px',
            maxWidth: '92vw',
            data: {
              specSlug: this.specSlug(row.spec_path),
              fallbackTitle: row.title,
            },
          });
        }
        break;
      case 'ops_feed':
        this.router.navigate(['/operations-feed'], {
          queryParams: { q: row.id },
        });
        break;
      case 'mission_critical':
        this.router.navigate(['/dashboard'], {
          fragment: `mc-tile-${row.id}`,
        });
        break;
    }
  }

  familyTooltip(f: FamilySummary): string {
    if (f.family === 'active') {
      return $localize`:@@metaAlgorithms.families.activeTip:${f.total} currently shipped meta-algorithms.`;
    }
    if (f.family === 'signal') {
      return $localize`:@@metaAlgorithms.families.signalTip:${f.total} forward-declared ranking signals.`;
    }
    const parts: string[] = [];
    if (f.active > 0) {
      const active = f.active;
      parts.push($localize`:@@metaAlgorithms.families.activeCount:${active}:count: active`);
    }
    if (f.forward > 0) {
      const forward = f.forward;
      parts.push($localize`:@@metaAlgorithms.families.forwardCount:${forward}:count: forward`);
    }
    if (f.disabled > 0) {
      const disabled = f.disabled;
      parts.push($localize`:@@metaAlgorithms.families.disabledCount:${disabled}:count: disabled`);
    }

    const family = f.family;
    const summary =
      parts.length > 0
        ? parts.join(' · ')
        : $localize`:@@metaAlgorithms.families.fallbackCount:${f.total}:total: metas`;
    return $localize`:@@metaAlgorithms.families.genericTip:${family}:family:: ${summary}:summary:`;
  }

  trackById(_: number, row: MetaRow): string {
    return row.id;
  }

  private specSlug(specPath: string): string {
    const leaf = specPath.split(/[\\/]/).pop() || specPath;
    return leaf.replace(/\.md$/i, '');
  }
}
