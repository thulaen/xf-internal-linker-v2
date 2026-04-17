import {
  ChangeDetectionStrategy,
  Component,
  ContentChildren,
  Directive,
  EventEmitter,
  Input,
  Output,
  QueryList,
  TemplateRef,
  computed,
  signal,
} from '@angular/core';
import { CommonModule, NgTemplateOutlet } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';

/**
 * Phase FR / Gap 109 — Multi-step wizard component.
 *
 * Reusable container for any multi-page form: import config wizards,
 * pipeline-setup walkthroughs, weighted-tuning sequences, etc.
 *
 * Usage:
 *
 *   <app-form-wizard
 *     [(activeStep)]="step"
 *     [completed]="completedSteps"
 *     (finish)="onFinish()"
 *   >
 *     <app-form-wizard-step label="Source" [valid]="form.controls.source.valid">
 *       <ng-template wizardStepContent>
 *         <!-- step 1 inputs -->
 *       </ng-template>
 *     </app-form-wizard-step>
 *
 *     <app-form-wizard-step label="Schedule" [valid]="form.controls.schedule.valid">
 *       <ng-template wizardStepContent>
 *         <!-- step 2 inputs -->
 *       </ng-template>
 *     </app-form-wizard-step>
 *
 *     <app-form-wizard-step label="Review">
 *       <ng-template wizardStepContent>
 *         <!-- review screen -->
 *       </ng-template>
 *     </app-form-wizard-step>
 *   </app-form-wizard>
 *
 * Features:
 *   - Progress bar showing completion percentage.
 *   - Numbered breadcrumb (1, 2, 3) with click-to-jump back.
 *   - Per-step `[valid]` input: Next is disabled until the step is valid.
 *   - Built-in Previous / Next / Finish buttons (configurable labels).
 *   - Emits (finish) on the last step.
 *
 * Why not just MatStepper: MatStepper is heavy and ties tightly to
 * Reactive Forms. This wrapper works with template-driven forms,
 * Reactive forms, or no forms at all (signals + manual valid state).
 */

/**
 * Marker directive on the <ng-template> inside each step. Lets us
 * pull out the actual content via @ContentChildren without forcing
 * the consumer to use *appWizardStepContent="" syntax.
 */
@Directive({
  selector: '[wizardStepContent]',
  standalone: true,
})
export class WizardStepContentDirective {
  constructor(public template: TemplateRef<unknown>) {}
}

/** A single wizard step. Wrap content inside <ng-template wizardStepContent>. */
@Component({
  selector: 'app-form-wizard-step',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<ng-content />',
})
export class FormWizardStepComponent {
  /** Short label rendered in the breadcrumb. */
  @Input({ required: true }) label = '';
  /** Whether the step's inputs are valid. Defaults to true so optional
   *  review steps don't require any flag. */
  @Input() valid = true;
  /** Optional explanatory subtitle shown beneath the label. */
  @Input() hint = '';

  @ContentChildren(WizardStepContentDirective)
  contentTemplates!: QueryList<WizardStepContentDirective>;
}

@Component({
  selector: 'app-form-wizard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    NgTemplateOutlet,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
  ],
  template: `
    <div class="fw">
      <header class="fw-header">
        <ol class="fw-crumbs">
          @for (step of stepArray(); track step.label; let i = $index) {
            <li class="fw-crumb"
                [class.fw-active]="i === activeStep"
                [class.fw-done]="i < activeStep"
                [class.fw-clickable]="i <= maxReachedStep()"
            >
              <button
                type="button"
                class="fw-crumb-btn"
                [disabled]="i > maxReachedStep()"
                (click)="jumpTo(i)"
              >
                <span class="fw-crumb-num">
                  @if (i < activeStep) {
                    <mat-icon class="fw-check-icon">check</mat-icon>
                  } @else {
                    {{ i + 1 }}
                  }
                </span>
                <span class="fw-crumb-text">
                  <span class="fw-crumb-label">{{ step.label }}</span>
                  @if (step.hint) {
                    <span class="fw-crumb-hint">{{ step.hint }}</span>
                  }
                </span>
              </button>
            </li>
          }
        </ol>
        <mat-progress-bar
          mode="determinate"
          [value]="progressPercent()"
          aria-label="Wizard progress"
        />
      </header>

      <section class="fw-body" aria-live="polite">
        @if (currentTemplate(); as t) {
          <ng-container *ngTemplateOutlet="t" />
        }
      </section>

      <footer class="fw-footer">
        <button
          mat-stroked-button
          type="button"
          [disabled]="activeStep === 0"
          (click)="previous()"
        >
          <mat-icon>arrow_back</mat-icon>
          {{ previousLabel }}
        </button>
        <span class="fw-spacer"></span>
        @if (isLastStep()) {
          <button
            mat-flat-button
            color="primary"
            type="button"
            [disabled]="!currentValid()"
            (click)="emitFinish()"
          >
            {{ finishLabel }}
            <mat-icon iconPositionEnd>check</mat-icon>
          </button>
        } @else {
          <button
            mat-flat-button
            color="primary"
            type="button"
            [disabled]="!currentValid()"
            (click)="next()"
          >
            {{ nextLabel }}
            <mat-icon iconPositionEnd>arrow_forward</mat-icon>
          </button>
        }
      </footer>
    </div>
  `,
  styles: [`
    .fw {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .fw-header { display: flex; flex-direction: column; gap: 12px; }
    .fw-crumbs {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .fw-crumb-btn {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      color: var(--color-text-secondary);
      cursor: pointer;
      font: inherit;
      transition: background-color 0.15s ease, border-color 0.15s ease;
    }
    .fw-crumb-btn:disabled { cursor: not-allowed; opacity: 0.65; }
    .fw-crumb.fw-active .fw-crumb-btn {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
      border-color: var(--color-primary);
    }
    .fw-crumb.fw-done .fw-crumb-btn {
      border-color: var(--color-success, #1e8e3e);
      color: var(--color-success-dark, #137333);
    }
    .fw-crumb-num {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: rgba(0, 0, 0, 0.08);
      color: inherit;
      font-weight: 600;
      font-size: 12px;
    }
    .fw-active .fw-crumb-num {
      background: rgba(255, 255, 255, 0.25);
    }
    .fw-check-icon { font-size: 14px; width: 14px; height: 14px; }
    .fw-crumb-text {
      display: inline-flex;
      flex-direction: column;
      align-items: flex-start;
      line-height: 1.2;
    }
    .fw-crumb-label { font-weight: 500; font-size: 13px; }
    .fw-crumb-hint  { font-size: 11px; color: inherit; opacity: 0.85; }
    .fw-body { min-height: 200px; }
    .fw-footer {
      display: flex;
      align-items: center;
      gap: 8px;
      padding-top: 16px;
      border-top: var(--card-border);
    }
    .fw-spacer { flex: 1; }
    @media (prefers-reduced-motion: reduce) {
      .fw-crumb-btn { transition: none; }
    }
  `],
})
export class FormWizardComponent {
  /** Active step index (0-based). Two-way bound. */
  @Input() activeStep = 0;
  @Output() activeStepChange = new EventEmitter<number>();

  @Input() previousLabel = 'Back';
  @Input() nextLabel = 'Next';
  @Input() finishLabel = 'Finish';

  @Output() finish = new EventEmitter<void>();

  @ContentChildren(FormWizardStepComponent)
  stepsQuery!: QueryList<FormWizardStepComponent>;

  /** Highest step the user has visited so far — controls back-jump
   *  enablement so they can only revisit pages they've seen. */
  private readonly _maxReached = signal<number>(0);
  readonly maxReachedStep = this._maxReached.asReadonly();

  readonly stepArray = signal<readonly FormWizardStepComponent[]>([]);

  ngAfterContentInit(): void {
    this.refreshSteps();
    this.stepsQuery.changes.subscribe(() => this.refreshSteps());
  }

  // ── derived state ──────────────────────────────────────────────────

  readonly progressPercent = computed(() => {
    const total = Math.max(1, this.stepArray().length);
    return Math.round(((this.activeStep + 1) / total) * 100);
  });

  isLastStep(): boolean {
    return this.activeStep >= this.stepArray().length - 1;
  }

  currentValid(): boolean {
    const s = this.stepArray()[this.activeStep];
    return s ? s.valid : true;
  }

  currentTemplate(): TemplateRef<unknown> | null {
    const s = this.stepArray()[this.activeStep];
    if (!s) return null;
    return s.contentTemplates?.first?.template ?? null;
  }

  // ── navigation ─────────────────────────────────────────────────────

  next(): void {
    if (!this.currentValid()) return;
    if (this.isLastStep()) return;
    this.setActive(this.activeStep + 1);
  }

  previous(): void {
    if (this.activeStep === 0) return;
    this.setActive(this.activeStep - 1);
  }

  jumpTo(index: number): void {
    if (index < 0 || index >= this.stepArray().length) return;
    if (index > this._maxReached()) return;
    this.setActive(index);
  }

  emitFinish(): void {
    if (!this.currentValid()) return;
    this.finish.emit();
  }

  // ── internals ──────────────────────────────────────────────────────

  private refreshSteps(): void {
    this.stepArray.set(this.stepsQuery.toArray());
    if (this._maxReached() < this.activeStep) {
      this._maxReached.set(this.activeStep);
    }
  }

  private setActive(index: number): void {
    this.activeStep = index;
    if (index > this._maxReached()) this._maxReached.set(index);
    this.activeStepChange.emit(index);
  }
}
