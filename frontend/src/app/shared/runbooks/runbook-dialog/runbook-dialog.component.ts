import { Component, inject, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { Runbook } from '../runbook-library';

@Component({
  selector: 'app-runbook-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule, MatChipsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>{{ runbook.title }}</h2>
    <mat-dialog-content>
      <section class="runbook-section">
        <h4 class="section-label">Problem</h4>
        <p class="section-text">{{ runbook.plainEnglishProblem }}</p>
      </section>

      <section class="runbook-section">
        <h4 class="section-label">Plan</h4>
        <ol class="step-list">
          @for (step of runbook.steps; track step.description) {
            <li [class.destructive]="step.isDestructive">
              {{ step.description }}
              @if (step.isDestructive) {
                <mat-chip class="destructive-chip" disableRipple>Requires confirmation</mat-chip>
              }
            </li>
          }
        </ol>
      </section>

      <div class="runbook-meta">
        <div class="meta-item">
          <span class="meta-label">Resource level</span>
          <mat-chip [class]="'resource-' + runbook.resourceLevel" disableRipple>
            {{ runbook.resourceLevel }}
          </mat-chip>
        </div>
        <div class="meta-item">
          <span class="meta-label">What it pauses</span>
          <span class="meta-value">{{ runbook.whatItWillPause }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Stop condition</span>
          <span class="meta-value">{{ runbook.stopCondition }}</span>
        </div>
      </div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" [mat-dialog-close]="true">
        Run this fix
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .runbook-section { margin-bottom: var(--space-lg); }
    .section-label {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--color-text-muted);
      margin: 0 0 var(--space-xs);
    }
    .section-text {
      font-size: 13px;
      color: var(--color-text-primary);
      margin: 0;
    }
    .step-list {
      padding-left: 20px;
      margin: 0;
    }
    .step-list li {
      font-size: 13px;
      color: var(--color-text-primary);
      margin-bottom: var(--space-sm);
      line-height: 1.5;
    }
    .step-list li.destructive { color: var(--color-error-dark); }
    .destructive-chip {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
      font-size: 10px;
      height: 20px;
      margin-left: var(--space-sm);
    }
    .runbook-meta {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
      padding: var(--space-md);
      background: var(--color-bg-faint);
      border-radius: var(--radius-md);
    }
    .meta-item { display: flex; align-items: center; gap: var(--space-sm); }
    .meta-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--color-text-muted);
      min-width: 100px;
    }
    .meta-value {
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .resource-low {
      --mdc-chip-elevated-container-color: var(--color-success-light);
      --mdc-chip-label-text-color: var(--color-success-dark);
    }
    .resource-medium {
      --mdc-chip-elevated-container-color: var(--color-warning-light);
      --mdc-chip-label-text-color: var(--color-warning-dark);
    }
    .resource-high {
      --mdc-chip-elevated-container-color: var(--color-error-50);
      --mdc-chip-label-text-color: var(--color-error-dark);
    }
  `],
})
export class RunbookDialogComponent {
  runbook = inject<Runbook>(MAT_DIALOG_DATA);
}
