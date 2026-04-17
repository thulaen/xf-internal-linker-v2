import { Directive, ElementRef, Input, OnChanges, SimpleChanges, inject } from '@angular/core';
import { AttentionPriority, ScrollAttentionService } from '../services/scroll-attention.service';

/**
 * Declarative attention-target directive.
 *
 * Usage:
 *   <div [appAttentionTarget]="isUrgent"
 *        [attentionPriority]="'urgent'"
 *        [attentionAnnounce]="'Pipeline failed — action required.'">...</div>
 *
 * Mechanics:
 *   - Host element is passed to ScrollAttentionService.drawTo() whenever
 *     the `[appAttentionTarget]` binding transitions from falsy to truthy.
 *   - The directive does NOT poll. It only fires on state transitions, so
 *     a tile that stays red does not spam the user with pulses.
 *   - Priority and optional announcement text are configurable per host.
 *
 * Phase GB / Gap 148 — complements ScrollAttentionService for template-
 * driven use. Programmatic callers can inject the service directly.
 */
@Directive({
  selector: '[appAttentionTarget]',
  standalone: true,
})
export class AttentionTargetDirective implements OnChanges {
  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly attention = inject(ScrollAttentionService);

  /**
   * When this binding flips from falsy to truthy, draw attention to the host.
   * Subsequent truthy renders do not re-trigger — the host must pass through
   * falsy to arm the next pulse. This is the dedup rule.
   */
  @Input('appAttentionTarget') armed: unknown = false;

  /** Priority level. Defaults to `'normal'`. */
  @Input() attentionPriority: AttentionPriority = 'normal';

  /** Optional plain-English announcement for screen readers. */
  @Input() attentionAnnounce?: string;

  private wasArmed = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (!('armed' in changes)) return;

    const nowArmed = !!this.armed;
    if (nowArmed && !this.wasArmed) {
      this.attention.drawTo(this.host.nativeElement, {
        priority: this.attentionPriority,
        announce: this.attentionAnnounce,
      });
    }
    this.wasArmed = nowArmed;
  }
}
