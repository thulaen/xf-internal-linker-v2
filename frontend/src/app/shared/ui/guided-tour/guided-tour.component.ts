import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  NgZone,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { GuidedTourService, TourStep } from '../../../core/services/guided-tour.service';

interface BubblePosition {
  top: number;
  left: number;
  /** Where the bubble's arrow points back to the target. */
  arrow: 'top' | 'bottom' | 'left' | 'right';
}

interface SpotlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/**
 * Phase D2 / Gap 70 — Guided tour overlay component.
 *
 * Renders a backdrop with a transparent "spotlight" cut out around the
 * current step's target, plus a tooltip bubble with title/body and
 * Previous / Next / Skip buttons.
 *
 * Uses raw position math instead of cdk-overlay so the spotlight can
 * follow window resize without depending on a positioning strategy
 * library that we'd otherwise only need here.
 */
@Component({
  selector: 'app-guided-tour',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule],
  template: `
    @if (tour() && step(); as s) {
      <div class="gt-backdrop" (click)="onSkip()">
        @if (rect(); as r) {
          <div
            class="gt-spotlight"
            [style.top.px]="r.top"
            [style.left.px]="r.left"
            [style.width.px]="r.width"
            [style.height.px]="r.height"
          ></div>
        }
        <div
          class="gt-bubble"
          [class.gt-arrow-top]="bubblePos().arrow === 'top'"
          [class.gt-arrow-bottom]="bubblePos().arrow === 'bottom'"
          [class.gt-arrow-left]="bubblePos().arrow === 'left'"
          [class.gt-arrow-right]="bubblePos().arrow === 'right'"
          [style.top.px]="bubblePos().top"
          [style.left.px]="bubblePos().left"
          (click)="$event.stopPropagation()"
          role="dialog"
          aria-labelledby="gt-title"
          aria-modal="true"
        >
          <header class="gt-head">
            <h3 id="gt-title" class="gt-title">{{ s.title }}</h3>
            <span class="gt-progress">
              {{ stepIndex() + 1 }} / {{ tour()!.steps.length }}
            </span>
          </header>
          <p class="gt-body">{{ s.body }}</p>
          <footer class="gt-actions">
            <button
              mat-button
              type="button"
              class="gt-skip"
              (click)="onSkip()"
            >
              Skip tour
            </button>
            <span class="gt-spacer"></span>
            <button
              mat-stroked-button
              type="button"
              [disabled]="stepIndex() === 0"
              (click)="onPrev()"
            >
              <mat-icon>arrow_back</mat-icon>
              Back
            </button>
            <button
              mat-raised-button
              color="primary"
              type="button"
              (click)="onNext()"
            >
              {{ isLastStep() ? 'Finish' : 'Next' }}
              @if (!isLastStep()) {
                <mat-icon iconPositionEnd>arrow_forward</mat-icon>
              }
            </button>
          </footer>
        </div>
      </div>
    }
  `,
  styles: [`
    .gt-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.55);
      z-index: 9994;
      cursor: pointer;
    }
    .gt-spotlight {
      position: fixed;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
      border-radius: 8px;
      pointer-events: none;
      transition: top 0.25s ease, left 0.25s ease, width 0.25s ease, height 0.25s ease;
    }
    .gt-bubble {
      position: fixed;
      width: 360px;
      max-width: calc(100vw - 32px);
      background: var(--color-bg-white);
      border-radius: var(--card-border-radius, 8px);
      box-shadow: var(--shadow-lg, 0 8px 24px rgba(60, 64, 67, 0.2));
      padding: 16px;
      cursor: default;
      transition: top 0.25s ease, left 0.25s ease;
    }
    .gt-bubble::before {
      content: '';
      position: absolute;
      width: 12px;
      height: 12px;
      background: var(--color-bg-white);
      transform: rotate(45deg);
    }
    .gt-arrow-top::before    { top: -6px;    left: 24px;  }
    .gt-arrow-bottom::before { bottom: -6px; left: 24px;  }
    .gt-arrow-left::before   { left: -6px;   top: 24px;   }
    .gt-arrow-right::before  { right: -6px;  top: 24px;   }
    .gt-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .gt-title {
      margin: 0;
      font-size: 15px;
      font-weight: 500;
      color: var(--color-text-primary);
    }
    .gt-progress {
      font-size: 11px;
      color: var(--color-text-secondary);
      font-variant-numeric: tabular-nums;
    }
    .gt-body {
      margin: 0 0 16px;
      font-size: 13px;
      line-height: 1.55;
      color: var(--color-text-secondary);
    }
    .gt-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .gt-spacer { flex: 1; }
    @media (prefers-reduced-motion: reduce) {
      .gt-spotlight, .gt-bubble { transition: none; }
    }
  `],
})
export class GuidedTourComponent {
  private readonly tourSvc = inject(GuidedTourService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly zone = inject(NgZone);
  private rafPending = false;

  readonly tour = this.tourSvc.activeTour;
  readonly stepIndex = this.tourSvc.stepIndex;
  readonly step = computed<TourStep | null>(() => {
    const t = this.tour();
    if (!t) return null;
    return t.steps[this.stepIndex()] ?? null;
  });
  readonly isLastStep = computed<boolean>(() => {
    const t = this.tour();
    if (!t) return false;
    return this.stepIndex() === t.steps.length - 1;
  });

  /** Recomputed every time the step changes, every scroll, every resize. */
  readonly rect = signal<SpotlightRect | null>(null);
  readonly bubblePos = signal<BubblePosition>({ top: 0, left: 0, arrow: 'top' });

  // Tracking handles for cleanup outside of effect's auto-cleanup. Both
  // route through scheduleRecompute() so a fast scroll never thrashes
  // layout — only one recompute per animation frame.
  private resizeHandler = () => this.scheduleRecompute();
  private scrollHandler = () => this.scheduleRecompute();

  constructor() {
    // Whenever the active step changes, re-pin the spotlight + bubble.
    effect(() => {
      const s = this.step();
      if (!s) {
        this.rect.set(null);
        return;
      }
      // Defer one frame so the DOM has time to layout if the tour
      // started simultaneously with a route change.
      requestAnimationFrame(() => this.recompute());
    });

    // Reposition on viewport changes while a tour is active.
    // Listen outside Angular's zone so a fast scroll doesn't trigger
    // global change detection on every pixel; the rAF-throttled
    // scheduleRecompute() re-enters the zone only when state actually
    // changes via signal updates.
    effect((onCleanup) => {
      if (!this.tour()) return;
      this.zone.runOutsideAngular(() => {
        window.addEventListener('resize', this.resizeHandler, { passive: true });
        window.addEventListener('scroll', this.scrollHandler, { passive: true, capture: true });
      });
      onCleanup(() => {
        window.removeEventListener('resize', this.resizeHandler);
        window.removeEventListener('scroll', this.scrollHandler, true);
      });
    });
  }

  private scheduleRecompute(): void {
    if (this.rafPending) return;
    this.rafPending = true;
    requestAnimationFrame(() => {
      this.rafPending = false;
      // recompute() writes to signals, which Angular handles without us
      // explicitly re-entering the zone — signal effects pick it up.
      this.recompute();
    });
  }

  /** ESC anywhere closes the tour. Same as the Skip button. */
  @HostListener('document:keydown.escape')
  onEsc(): void {
    if (this.tour()) this.onSkip();
  }

  onNext(): void {
    this.tourSvc.next();
  }

  onPrev(): void {
    this.tourSvc.previous();
  }

  onSkip(): void {
    this.tourSvc.skip();
  }

  // ── positioning ────────────────────────────────────────────────────

  private recompute(): void {
    const s = this.step();
    if (!s) return;

    const target = document.querySelector<HTMLElement>(s.selector);
    if (!target) {
      // Target not present (e.g. wrong route). Clear spotlight; bubble
      // stays centred on screen as a fallback.
      this.rect.set(null);
      this.bubblePos.set({
        top: window.innerHeight / 2 - 100,
        left: window.innerWidth / 2 - 180,
        arrow: 'top',
      });
      return;
    }

    // Pull target into view if it's offscreen.
    const r = target.getBoundingClientRect();
    if (r.bottom < 0 || r.top > window.innerHeight) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Recompute after the scroll completes. Use scheduleRecompute() so
      // a settling scroll-into-view animation (which fires many scroll
      // events) doesn't enqueue N nested setTimeouts.
      setTimeout(() => this.scheduleRecompute(), 350);
      return;
    }

    const PAD = 8;
    const spot: SpotlightRect = {
      top: Math.max(0, r.top - PAD),
      left: Math.max(0, r.left - PAD),
      width: r.width + PAD * 2,
      height: r.height + PAD * 2,
    };
    this.rect.set(spot);

    // Place the bubble. Default = below; flip if it would overflow.
    const bubbleW = 360;
    const bubbleH = 220;
    const placement = s.placement ?? 'bottom';
    let pos: BubblePosition;

    switch (placement) {
      case 'top':
        pos = {
          top: spot.top - bubbleH - 12,
          left: spot.left,
          arrow: 'bottom',
        };
        break;
      case 'left':
        pos = {
          top: spot.top,
          left: spot.left - bubbleW - 12,
          arrow: 'right',
        };
        break;
      case 'right':
        pos = {
          top: spot.top,
          left: spot.left + spot.width + 12,
          arrow: 'left',
        };
        break;
      case 'bottom':
      default:
        pos = {
          top: spot.top + spot.height + 12,
          left: spot.left,
          arrow: 'top',
        };
    }

    // Clamp so the bubble stays on screen.
    pos.left = Math.min(
      Math.max(8, pos.left),
      window.innerWidth - bubbleW - 8,
    );
    pos.top = Math.min(
      Math.max(8, pos.top),
      window.innerHeight - bubbleH - 8,
    );

    this.bubblePos.set(pos);
  }
}
