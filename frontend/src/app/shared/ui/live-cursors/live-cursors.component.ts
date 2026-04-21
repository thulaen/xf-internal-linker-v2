import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Input,
  NgZone,
  OnInit,
  Renderer2,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../../core/services/auth.service';
import { PresenceService } from '../../../core/services/presence.service';
import { RealtimeService } from '../../../core/services/realtime.service';

/**
 * Phase RC / Gap 140 — Collaborator cursors.
 *
 * Drop on a "shared" page (typically a review queue or a settings
 * editor) where multiple operators may want to see each other's
 * pointer. Coordinates broadcast at 12 Hz max (every 80ms) to keep
 * bandwidth + CPU sane.
 *
 *   <app-live-cursors topic="cursor.review-123" />
 *
 * The topic name is parent-supplied so different shared screens
 * don't bleed into each other (per-suggestion, per-graph, per-form).
 *
 * Shows up to 8 colored arrow cursors, one per remote peer. Self
 * cursor is hidden (the OS already shows it).
 */

interface CursorPayload {
  x: number;
  y: number;
  /** Username overlaid next to the cursor. */
  username: string;
}

interface RemoteCursor {
  username: string;
  x: number;
  y: number;
  color: string;
  lastSeen: number;
  connectionId: string;
}

const STALE_MS = 5_000;
const SEND_INTERVAL_MS = 80;
const COLORS = ['#1a73e8', '#1e8e3e', '#f9ab00', '#d93025', '#a142f4', '#16a2b8', '#e91e63', '#795548'];

@Component({
  selector: 'app-live-cursors',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  template: `
    <div class="lc-overlay" aria-hidden="true">
      @for (c of remote(); track c.connectionId) {
        <div
          class="lc-cursor"
          [style.left.px]="c.x"
          [style.top.px]="c.y"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" [attr.fill]="c.color">
            <path d="M2 2 L18 9 L9 11 L7 18 Z" />
          </svg>
          <span class="lc-label" [style.background]="c.color">{{ c.username }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .lc-overlay {
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 9994;
    }
    .lc-cursor {
      position: absolute;
      transform: translate(-2px, -2px);
      transition: top 0.06s linear, left 0.06s linear;
      will-change: transform;
    }
    .lc-label {
      display: inline-block;
      margin-left: 4px;
      padding: 1px 6px;
      border-radius: 8px;
      color: #fff;
      font-size: 10px;
      font-family: var(--font-family);
      vertical-align: top;
    }
    @media (prefers-reduced-motion: reduce) {
      .lc-cursor { transition: none; }
    }
  `],
})
export class LiveCursorsComponent implements OnInit {
  /** Topic to publish/subscribe on. Required.
   *  Must start with `cursor.` so the backend authorises publish. */
  @Input({ required: true }) topic = '';

  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly presence = inject(PresenceService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly ngZone = inject(NgZone);
  private readonly renderer = inject(Renderer2);

  private myUsername = '';
  private myConnectionId = '';
  private lastSentAt = 0;
  private sendTimer: ReturnType<typeof setTimeout> | null = null;
  private pendingX = 0;
  private pendingY = 0;
  private hasPending = false;

  private readonly _cursors = signal<ReadonlyMap<string, RemoteCursor>>(new Map());

  readonly remote = computed(() => {
    const cutoff = Date.now() - STALE_MS;
    return [...this._cursors().values()]
      .filter((c) => c.lastSeen >= cutoff && c.connectionId !== this.myConnectionId)
      .slice(0, 8);
  });

  ngOnInit(): void {
    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => (this.myUsername = u?.username ?? ''));

    this.realtime
      .subscribeTopic<CursorPayload & { _publisher?: { username?: string; connection_id?: string } }>(
        this.topic,
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => {
        const pub = u.payload?._publisher;
        if (!pub?.connection_id) return;
        if (pub.username === this.myUsername && !this.myConnectionId) {
          this.myConnectionId = pub.connection_id;
          // Don't render our own cursor; bail.
          return;
        }
        if (pub.connection_id === this.myConnectionId) return;
        const next = new Map(this._cursors());
        next.set(pub.connection_id, {
          username: pub.username || 'unknown',
          x: u.payload.x,
          y: u.payload.y,
          color: this.colorFor(pub.connection_id),
          lastSeen: Date.now(),
          connectionId: pub.connection_id,
        });
        this._cursors.set(next);
      });

    // Listen for cursor moves OUTSIDE the Angular zone. A
    // `@HostListener('document:mousemove')` is registered through
    // Angular's event manager which re-enters the zone on every
    // emission — at ~100 events/sec that pins change detection to
    // the mouse. The handler here only mutates local fields and
    // schedules a throttled WebSocket publish, so it never needs
    // to touch Angular state. See docs/PERFORMANCE.md §13.
    this.ngZone.runOutsideAngular(() => {
      const off = this.renderer.listen('document', 'mousemove', (event: MouseEvent) => {
        if (!this.myUsername || !this.topic) return;
        this.pendingX = event.clientX;
        this.pendingY = event.clientY;
        this.hasPending = true;
        this.scheduleSend();
      });
      this.destroyRef.onDestroy(off);
    });
  }

  // ── helpers ────────────────────────────────────────────────────────

  private scheduleSend(): void {
    if (this.sendTimer) return;
    const elapsed = Date.now() - this.lastSentAt;
    const wait = Math.max(0, SEND_INTERVAL_MS - elapsed);
    this.sendTimer = setTimeout(() => {
      this.sendTimer = null;
      if (!this.hasPending) return;
      this.hasPending = false;
      this.lastSentAt = Date.now();
      this.realtime.publish(this.topic, 'move', {
        x: this.pendingX,
        y: this.pendingY,
        username: this.myUsername,
      });
    }, wait);
  }

  private colorFor(connectionId: string): string {
    let hash = 0;
    for (let i = 0; i < connectionId.length; i++) {
      hash = ((hash << 5) - hash) + connectionId.charCodeAt(i);
      hash |= 0;
    }
    return COLORS[Math.abs(hash) % COLORS.length];
  }
}
