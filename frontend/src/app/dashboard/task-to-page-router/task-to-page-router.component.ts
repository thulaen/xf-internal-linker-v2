import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';

/**
 * Phase D1 / Gap 60 — Task-to-Page Router.
 *
 * A `<select>`-style dropdown of common operator intents, each mapped to
 * a concrete route. Distinct from Gap 57 (free-text "I want to…"
 * autocomplete) by UX: this is a structured menu of approved tasks,
 * ideal when the operator knows what they want but not WHERE it lives.
 *
 * Intent rows are the same taxonomy as Command Suggestions but
 * presented differently (grouped, no typing). Keeping two surfaces
 * lets us A/B future taxonomy changes without forking.
 */

interface IntentGroup {
  heading: string;
  options: readonly IntentOption[];
}

interface IntentOption {
  label: string;
  route: string;
  fragment?: string;
  icon: string;
}

const INTENT_GROUPS: readonly IntentGroup[] = [
  {
    heading: 'Review',
    options: [
      { label: 'Approve pending link suggestions', route: '/review', icon: 'rate_review' },
      { label: 'Check what changed in the last day', route: '/dashboard', fragment: 'what-changed', icon: 'update' },
      { label: 'Open the Alerts center', route: '/alerts', icon: 'notifications' },
    ],
  },
  {
    heading: 'Data',
    options: [
      { label: 'Import content from XenForo or WordPress', route: '/jobs', icon: 'upload_file' },
      { label: 'Run a full pipeline', route: '/dashboard', fragment: 'today-focus', icon: 'play_arrow' },
      { label: 'Start a web crawl', route: '/crawler', icon: 'travel_explore' },
    ],
  },
  {
    heading: 'Quality',
    options: [
      { label: 'Scan for broken links', route: '/link-health', icon: 'link_off' },
      { label: 'Look for orphan pages', route: '/graph', fragment: 'orphans', icon: 'account_tree' },
      { label: 'Explore behavioral hubs', route: '/behavioral-hubs', icon: 'hub' },
    ],
  },
  {
    heading: 'Tune',
    options: [
      { label: 'Adjust ranking weights', route: '/settings', fragment: 'weights', icon: 'tune' },
      { label: 'Switch runtime / performance mode', route: '/dashboard', fragment: 'performance-mode', icon: 'speed' },
      { label: 'Pause everything', route: '/dashboard', fragment: 'today-focus', icon: 'pause_circle' },
    ],
  },
  {
    heading: 'Investigate',
    options: [
      { label: 'Check system health', route: '/health', icon: 'health_and_safety' },
      { label: 'Open the Error Log', route: '/error-log', icon: 'bug_report' },
      { label: 'Review benchmark results', route: '/performance', icon: 'monitoring' },
    ],
  },
];

@Component({
  selector: 'app-task-to-page-router',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
  ],
  template: `
    <mat-card class="ttp-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="ttp-avatar">explore</mat-icon>
        <mat-card-title>Take me to…</mat-card-title>
        <mat-card-subtitle>Pick an intent; we'll open the right page.</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <mat-form-field appearance="outline" class="ttp-field">
          <mat-label>I want to…</mat-label>
          <mat-select [(value)]="selected" (selectionChange)="onPick(selected)">
            @for (group of groups; track group.heading) {
              <mat-optgroup [label]="group.heading">
                @for (opt of group.options; track opt.label) {
                  <mat-option [value]="opt">
                    <mat-icon class="ttp-option-icon">{{ opt.icon }}</mat-icon>
                    <span>{{ opt.label }}</span>
                  </mat-option>
                }
              </mat-optgroup>
            }
          </mat-select>
        </mat-form-field>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .ttp-card { height: 100%; }
    .ttp-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .ttp-field { width: 100%; }
    .ttp-option-icon {
      margin-right: 8px;
      color: var(--color-text-secondary);
      font-size: 18px;
      width: 18px;
      height: 18px;
      vertical-align: middle;
    }
  `],
})
export class TaskToPageRouterComponent {
  private readonly router = inject(Router);

  readonly groups = INTENT_GROUPS;
  selected: IntentOption | null = null;

  onPick(opt: IntentOption | null): void {
    if (!opt) return;
    this.router.navigate([opt.route], {
      fragment: opt.fragment,
    });
    // Reset so the same intent can be picked again on return.
    queueMicrotask(() => {
      this.selected = null;
    });
  }
}
