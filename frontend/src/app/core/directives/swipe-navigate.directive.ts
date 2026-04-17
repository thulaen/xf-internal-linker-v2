import {
  Directive,
  ElementRef,
  HostListener,
  inject,
  Input,
  OnInit,
  signal,
} from '@angular/core';
import { Location } from '@angular/common';
import { Router } from '@angular/router';

/**
 * Phase NV / Gap 144 — Mobile swipe gestures for browser-history navigation.
 *
 * Attach to a container element (e.g. <main>) to give touch users a familiar
 * swipe-from-edge back/forward gesture. Pointer-type checks ensure mouse and
 * stylus swipes don't accidentally fire — only `touch` and `pen` count.
 *
 * Heuristics chosen to avoid false positives:
 *   • Swipe must START within `edgeZonePx` of the screen edge (default 32px).
 *     Center swipes are usually scrolling intent, not navigation.
 *   • Horizontal travel must exceed `minTravelPx` (default 64px).
 *   • Horizontal travel must be at least 1.8× vertical travel — otherwise
 *     the user is scrolling, not swiping.
 *   • Total gesture time must be under `maxDurationMs` (default 600ms).
 *
 * Right-swipe from left edge → history.back().
 * Left-swipe from right edge → history.forward().
 *
 * Respects users navigating to /login or with `data-no-swipe-nav="true"`
 * on any ancestor of the touch target — avoids hijacking embedded carousels.
 */
@Directive({
  selector: '[appSwipeNavigate]',
  standalone: true,
})
export class SwipeNavigateDirective implements OnInit {
  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private location = inject(Location);
  private router = inject(Router);

  @Input() edgeZonePx = 32;
  @Input() minTravelPx = 64;
  @Input() maxDurationMs = 600;

  private startX = 0;
  private startY = 0;
  private startedAt = 0;
  private armed = signal(false);
  private startedFromOptOut = false;

  ngOnInit(): void {
    // Defensive: ensure host has touch-action that lets us read swipes.
    // Don't override if author already set it.
    const el = this.host.nativeElement;
    if (!el.style.touchAction) el.style.touchAction = 'pan-y';
  }

  @HostListener('pointerdown', ['$event'])
  onPointerDown(ev: PointerEvent): void {
    if (ev.pointerType !== 'touch' && ev.pointerType !== 'pen') {
      this.armed.set(false);
      return;
    }
    const target = ev.target as HTMLElement | null;
    this.startedFromOptOut = !!target?.closest('[data-no-swipe-nav="true"]');
    if (this.startedFromOptOut) {
      this.armed.set(false);
      return;
    }
    const w = window.innerWidth;
    const fromLeft = ev.clientX <= this.edgeZonePx;
    const fromRight = ev.clientX >= w - this.edgeZonePx;
    if (!fromLeft && !fromRight) {
      this.armed.set(false);
      return;
    }
    this.armed.set(true);
    this.startX = ev.clientX;
    this.startY = ev.clientY;
    this.startedAt = ev.timeStamp;
  }

  @HostListener('pointerup', ['$event'])
  onPointerUp(ev: PointerEvent): void {
    if (!this.armed()) return;
    this.armed.set(false);
    if (ev.pointerType !== 'touch' && ev.pointerType !== 'pen') return;

    const dx = ev.clientX - this.startX;
    const dy = ev.clientY - this.startY;
    const dt = ev.timeStamp - this.startedAt;
    if (dt > this.maxDurationMs) return;

    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    if (absX < this.minTravelPx) return;
    if (absX < absY * 1.8) return;

    // Don't navigate away from /login — would strand the user.
    if (this.router.url.startsWith('/login')) return;

    if (dx > 0 && this.startX <= this.edgeZonePx) {
      // Right swipe from left edge → go back
      this.location.back();
    } else if (dx < 0 && this.startX >= window.innerWidth - this.edgeZonePx) {
      // Left swipe from right edge → go forward
      this.location.forward();
    }
  }

  @HostListener('pointercancel')
  onPointerCancel(): void {
    this.armed.set(false);
  }
}
