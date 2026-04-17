import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  PIPELINE_STAGES,
  PipelineStageId,
  PipelineStageMeta,
} from './pipeline-stage-map';

/**
 * Phase MX2 / Gaps 295, 296, 305 — plain-English pipeline visual.
 *
 * Three render modes sharing the same stage-map source of truth:
 *   * `mode="diagram"`  — static left-to-right dependency diagram
 *                         (Gap 295: "architecture simplified diagram").
 *   * `mode="journey"`  — stepped animation showing a single item's
 *                         progress through stages; `currentStage`
 *                         highlights position (Gap 296).
 *   * `mode="dag"`      — live DAG view with progress pulse per stage;
 *                         `activeStages` lights the running ones
 *                         (Gap 305).
 *
 * Keeps its own styling — no SVG library. Flexbox + CSS custom
 * properties deliver a perfectly-crisp result at any width. Respects
 * `prefers-reduced-motion` — animations collapse to instant paints.
 */
@Component({
  selector: 'app-pipeline-flow',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    <ol class="pf-row" [attr.data-mode]="mode">
      @for (stage of stages(); track stage.id) {
        <li
          class="pf-stage"
          [ngClass]="stageClass(stage)"
          [matTooltip]="stage.tooltip"
          [attr.aria-current]="isCurrent(stage.id) ? 'step' : null"
        >
          <span class="pf-icon">
            <mat-icon>{{ stage.icon }}</mat-icon>
          </span>
          <span class="pf-body">
            <span class="pf-title">{{ stage.title }}</span>
            <span class="pf-subtitle">{{ stage.subtitle }}</span>
          </span>
          <span class="pf-arrow" aria-hidden="true">→</span>
        </li>
      }
    </ol>
  `,
  styles: [`
    :host { display: block; overflow-x: auto; }
    .pf-row {
      display: flex;
      list-style: none;
      padding: 0;
      margin: 0;
      gap: 8px;
      flex-wrap: nowrap;
      min-width: max-content;
    }
    .pf-stage {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px;
      border: 0.8px solid var(--color-border, #dadce0);
      border-radius: 6px;
      background: var(--color-bg, #ffffff);
      min-width: 120px;
      position: relative;
      transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), background 0.2s;
    }
    .pf-icon mat-icon {
      width: 24px;
      height: 24px;
      font-size: 24px;
      color: var(--color-text-secondary, #5f6368);
    }
    .pf-stage-color-primary  .pf-icon mat-icon { color: var(--color-primary, #1a73e8); }
    .pf-stage-color-info     .pf-icon mat-icon { color: var(--color-blue-600, #1967d2); }
    .pf-stage-color-success  .pf-icon mat-icon { color: var(--color-success, #1e8e3e); }
    .pf-stage-color-warning  .pf-icon mat-icon { color: var(--color-warning, #f9ab00); }
    .pf-body { display: flex; flex-direction: column; min-width: 0; }
    .pf-title {
      font-weight: 500;
      font-size: 13px;
      color: var(--color-text-primary, #202124);
    }
    .pf-subtitle {
      font-size: 11px;
      color: var(--color-text-secondary, #5f6368);
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pf-arrow {
      font-size: 16px;
      color: var(--color-text-secondary, #5f6368);
      margin-left: 4px;
    }
    .pf-stage:last-child .pf-arrow { display: none; }
    .pf-stage-active {
      background: var(--color-bg-faint, #f1f3f4);
      box-shadow: inset 3px 0 0 var(--color-primary, #1a73e8);
    }
    .pf-stage-current {
      background: #e8f0fe;
      box-shadow: inset 3px 0 0 var(--color-primary, #1a73e8);
      transform: scale(1.02);
    }
    .pf-stage-done {
      opacity: 0.7;
    }
    .pf-stage-pulse {
      animation: pf-pulse 1.6s ease-in-out infinite;
    }
    @keyframes pf-pulse {
      0%, 100% { box-shadow: inset 3px 0 0 var(--color-primary); }
      50% { box-shadow: inset 3px 0 0 var(--color-primary), 0 0 0 4px rgba(26,115,232,0.12); }
    }
    @media (prefers-reduced-motion: reduce) {
      .pf-stage-pulse { animation: none; }
      .pf-stage-current { transform: none; }
    }
  `],
})
export class PipelineFlowComponent {
  @Input() mode: 'diagram' | 'journey' | 'dag' = 'diagram';
  @Input() currentStage: PipelineStageId | null = null;
  /** DAG mode only: which stages are currently processing. */
  @Input() set activeStagesList(v: PipelineStageId[] | null) {
    this._activeStages.set(new Set(v ?? []));
  }

  private readonly _activeStages = signal<Set<PipelineStageId>>(new Set());

  protected readonly stages = computed(() => PIPELINE_STAGES);

  stageClass(stage: PipelineStageMeta): string[] {
    const classes = [`pf-stage-color-${stage.color}`];
    if (this.mode === 'journey' || this.mode === 'diagram') {
      if (this.currentStage) {
        const idx = PIPELINE_STAGES.findIndex((s) => s.id === this.currentStage);
        const mine = PIPELINE_STAGES.findIndex((s) => s.id === stage.id);
        if (mine < idx) classes.push('pf-stage-done');
        if (mine === idx) classes.push('pf-stage-current');
      }
    }
    if (this.mode === 'dag' && this._activeStages().has(stage.id)) {
      classes.push('pf-stage-active', 'pf-stage-pulse');
    }
    return classes;
  }

  isCurrent(id: PipelineStageId): boolean {
    return this.currentStage === id;
  }
}
