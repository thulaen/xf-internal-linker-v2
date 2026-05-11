import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MetaRow } from './meta-algorithms.service';

/**
 * Phase MS — single meta-algorithm row.
 *
 * Renders in virtual scroll viewport — must be cheap. OnPush + no HTTP.
 * Two outputs: the toggle change and the action menu selection (Run
 * now / Open spec / View in Ops Feed / View in Mission Critical).
 */
@Component({
  selector: 'app-meta-row',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatSlideToggleModule,
    MatTooltipModule,
  ],
  template: `
    <div class="mr-row" [attr.data-id]="row.id">
      <span class="mr-family" [matTooltip]="familyTooltip()">{{ row.family }}</span>
      <span class="mr-code" [matTooltip]="row.meta_code || notAssignedLabel" i18n-matTooltip="@@metaAlgorithms.row.notAssignedTip">
        {{ row.meta_code || '—' }}
      </span>
      <span class="mr-title">
        {{ row.title }}
        @if (row.cpp_kernel) {
          <mat-icon class="mr-icon mr-cpp" [matTooltip]="cppTooltip(row.cpp_kernel)">
            bolt
          </mat-icon>
        }
      </span>
      <span class="mr-status" [ngClass]="'mr-status-' + row.status">
        {{ statusLabel() }}
      </span>
      @if (row.weight_value) {
        <span class="mr-weight" matTooltip="Weight value (read-only here; edit in Weight Diagnostics)" i18n-matTooltip="@@metaAlgorithms.row.weightTip">
          w = {{ row.weight_value }}
        </span>
      } @else {
        <span class="mr-weight mr-weight-empty">—</span>
      }
      <mat-slide-toggle
        class="mr-toggle"
        [checked]="row.enabled"
        [disabled]="row.status === 'disabled-pending-implementation'"
        (change)="toggled.emit({ id: row.id, enabled: $event.checked })"
        [attr.aria-label]="toggleAriaLabel"
      />
      <button
        mat-icon-button
        type="button"
        class="mr-actions"
        [matMenuTriggerFor]="menu"
        aria-label="More actions"
        i18n-aria-label="@@metaAlgorithms.row.actionsAria"
      >
        <mat-icon>more_vert</mat-icon>
      </button>
      <mat-menu #menu="matMenu" class="ga4-menu">
        <button
          mat-menu-item
          type="button"
          [disabled]="!row.enabled || row.status !== 'active'"
          (click)="actionClick.emit({ id: row.id, action: 'run' })"
        >
          <mat-icon>play_arrow</mat-icon>
          <ng-container i18n="@@metaAlgorithms.row.runBtn">Run now</ng-container>
        </button>
        <button
          mat-menu-item
          type="button"
          [disabled]="!row.spec_path"
          (click)="actionClick.emit({ id: row.id, action: 'spec' })"
        >
          <mat-icon>description</mat-icon>
          <ng-container i18n="@@metaAlgorithms.row.viewSpecBtn">View spec</ng-container>
        </button>
        <button
          mat-menu-item
          type="button"
          (click)="actionClick.emit({ id: row.id, action: 'ops_feed' })"
        >
          <mat-icon>rss_feed</mat-icon>
          <ng-container i18n="@@metaAlgorithms.row.opsFeedBtn">Show in Ops Feed</ng-container>
        </button>
        <button
          mat-menu-item
          type="button"
          (click)="actionClick.emit({ id: row.id, action: 'mission_critical' })"
        >
          <mat-icon>dashboard_customize</mat-icon>
          <ng-container i18n="@@metaAlgorithms.row.dashboardBtn">Show in Mission Critical</ng-container>
        </button>
      </mat-menu>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .mr-row {
      display: grid;
      grid-template-columns: 56px 88px 1fr 112px 96px 48px 40px;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border-bottom: 0.8px solid var(--color-border, #dadce0);
      font-size: 13px;
      min-height: 44px;
    }
    .mr-row:hover {
      background: var(--color-bg-faint, #f8f9fa);
    }
    .mr-family {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.4px;
      padding: 2px 6px;
      background: var(--color-bg-faint, #f1f3f4);
      color: var(--color-text-secondary, #5f6368);
      border-radius: 3px;
      text-align: center;
    }
    .mr-code {
      font-family: var(--font-family-mono, monospace);
      font-size: 11px;
      color: var(--color-text-secondary, #5f6368);
    }
    .mr-title {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--color-text-primary, #202124);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .mr-icon {
      width: 16px;
      height: 16px;
      font-size: 16px;
    }
    .mr-cpp { color: var(--color-primary, #1a73e8); }
    .mr-status {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      text-align: center;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .mr-status-active { background: #e6f4ea; color: #137333; }
    .mr-status-forward-declared { background: #f1f3f4; color: #5f6368; }
    .mr-status-disabled-pending-implementation { background: #f1f3f4; color: #5f6368; }
    .mr-status-disabled { background: #fce8e6; color: #c5221f; }
    .mr-weight {
      font-variant-numeric: tabular-nums;
      font-size: 12px;
      color: var(--color-text-secondary, #5f6368);
    }
    .mr-weight-empty { font-style: italic; }
    .mr-toggle { justify-self: center; }
    .mr-actions { justify-self: end; }
  `],
})
export class MetaRowComponent {
  @Input({ required: true }) row!: MetaRow;

  @Output() toggled = new EventEmitter<{ id: string; enabled: boolean }>();
  @Output() actionClick = new EventEmitter<{ id: string; action: string }>();

  get notAssignedLabel(): string {
    return $localize`:@@metaAlgorithms.row.notAssigned:Not assigned`;
  }

  statusLabel(): string {
    switch (this.row.status) {
      case 'active': return $localize`:@@metaAlgorithms.status.active:Active`;
      case 'disabled': return $localize`:@@metaAlgorithms.status.disabled:Disabled`;
      case 'disabled-pending-implementation': return $localize`:@@metaAlgorithms.status.spec:Spec only`;
      case 'forward-declared': return $localize`:@@metaAlgorithms.status.forward:Forward`;
      default: return this.row.status;
    }
  }

  familyTooltip(): string {
    const f = this.row.family;
    if (f === 'active') return $localize`:@@metaAlgorithms.family.activeTip:Currently shipped — wired into the pipeline.`;
    if (f === 'signal') return $localize`:@@metaAlgorithms.family.signalTip:Forward-declared ranking signal.`;
    if (f.startsWith('P')) return $localize`:@@metaAlgorithms.family.optTip:Optimiser block ${f}:family: — see docs/specs/.`;
    if (f.startsWith('Q')) return $localize`:@@metaAlgorithms.family.advTip:Advanced-methods block ${f}:family: — see docs/specs/.`;
    return $localize`:@@metaAlgorithms.family.genericTip:Family ${f}:family:`;
  }

  cppTooltip(kernel: string): string {
    return $localize`:@@metaAlgorithms.row.cppTip:C++ accelerated: ${kernel}:kernel:`;
  }

  get toggleAriaLabel(): string {
    const title = this.row.title;
    return $localize`:@@metaAlgorithms.row.toggleAria:Enable ${title}:title:`;
  }
}
