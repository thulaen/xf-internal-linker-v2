import {
  Directive,
  ElementRef,
  Input,
  Renderer2,
  inject,
  OnChanges,
  SimpleChanges,
} from '@angular/core';
import { PIPELINE_STAGES, PipelineStageId } from '../../shared/ui/pipeline-flow/pipeline-stage-map';

/**
 * Phase MX2 / Gaps 297, 298 — colour-coded stage dots on table rows.
 *
 * Attach to any row/card element:
 *
 *   <tr [appStageIndicator]="row.current_stage">...</tr>
 *
 * The directive paints a 4px-wide left stripe in the canonical colour
 * for the passed stage id (see `pipeline-stage-map.ts`) and sets the
 * row's `title` (native tooltip) to the stage's plain-English
 * description so a hover explains what's happening without opening
 * the detail pane.
 */
@Directive({
  selector: '[appStageIndicator]',
  standalone: true,
})
export class StageIndicatorDirective implements OnChanges {
  @Input('appStageIndicator') stageId: PipelineStageId | null = null;

  private el = inject<ElementRef<HTMLElement>>(ElementRef);
  private renderer = inject(Renderer2);

  ngOnChanges(changes: SimpleChanges): void {
    if ('stageId' in changes) this.apply();
  }

  private apply(): void {
    const host = this.el.nativeElement;
    if (!this.stageId) {
      this.renderer.removeStyle(host, 'border-left');
      this.renderer.removeAttribute(host, 'title');
      return;
    }
    const meta = PIPELINE_STAGES.find((s) => s.id === this.stageId);
    if (!meta) return;
    const cssVar = {
      primary: 'var(--color-primary, #1a73e8)',
      info: 'var(--color-blue-600, #1967d2)',
      success: 'var(--color-success, #1e8e3e)',
      warning: 'var(--color-warning, #f9ab00)',
    }[meta.color];
    this.renderer.setStyle(host, 'border-left', `4px solid ${cssVar}`);
    this.renderer.setAttribute(host, 'title', `${meta.title} — ${meta.subtitle}`);
  }
}
