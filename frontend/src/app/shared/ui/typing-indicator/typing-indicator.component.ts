import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  Input,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../../core/services/auth.service';
import { RealtimeService } from '../../../core/services/realtime.service';

/**
 * Phase RC / Gap 142 — "Alice is typing…" form indicator.
 *
 * Drop inside (or just below) a shared form to surface that another
 * operator is currently typing. The component listens for `input`
 * events on its parent element via host-listener, throttles them to
 * one publish per 1.5s, and renders other peers' typing notices for
 * 4 seconds after their last keystroke.
 *
 * Usage:
 *
 *   <form [formGroup]="form" (ngSubmit)="save()">
 *     <app-typing-indicator topic="typing.suggestion-123" />
 *     <mat-form-field>...</mat-form-field>
 *   </form>
 *
 * Topic naming convention: `typing.<resource>-<id>`. Topic must
 * start with `typing.` to satisfy backend publish authorisation.
 */

const SEND_INTERVAL_MS = 1500;
const STALE_AFTER_MS = 4000;

interface TypingPeer {
  username: string;
  lastSeen: number;
  connectionId: string;
}

@Component({
  selector: 'app-typing-indicator',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  template: `
    @if (others().length > 0) {
      <div class="ti" role="status" aria-live="polite">
        <span class="ti-dots" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
        <span class="ti-text">{{ label() }}</span>
      </div>
    }
  `,
  styles: [`
    .ti {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: var(--color-bg-faint);
      border-radius: 12px;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .ti-dots {
      display: inline-flex;
      gap: 2px;
    }
    .ti-dots span {
      width: 4px;
      height: 4px;
      background: var(--color-primary);
      border-radius: 50%;
      animation: ti-bounce 1.2s ease-in-out infinite;
    }
    .ti-dots span:nth-child(2) { animation-delay: 0.2s; }
    .ti-dots span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes ti-bounce {
      0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
      40%           { transform: translateY(-3px); opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
      .ti-dots span { animation: none; }
    }
  `],
})
export class TypingIndicatorComponent implements OnInit {
  /** Topic to publish/subscribe on. Must start with `typing.`. */
  @Input({ required: true }) topic = '';

  private readonly auth = inject(AuthService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);

  private myUsername = '';
  private myConnectionId = '';
  private lastSentAt = 0;

  private readonly _peers = signal<ReadonlyMap<string, TypingPeer>>(new Map());

  readonly others = computed(() => {
    const cutoff = Date.now() - STALE_AFTER_MS;
    return [...this._peers().values()]
      .filter((p) => p.lastSeen >= cutoff)
      .filter((p) => p.connectionId !== this.myConnectionId);
  });

  readonly label = computed(() => {
    const o = this.others();
    if (o.length === 0) return '';
    if (o.length === 1) return `${o[0].username} is editing…`;
    if (o.length === 2) return `${o[0].username} and ${o[1].username} are editing…`;
    return `${o.length} others are editing…`;
  });

  ngOnInit(): void {
    this.auth.currentUser$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => (this.myUsername = u?.username ?? ''));

    this.realtime
      .subscribeTopic<{
        username?: string;
        _publisher?: { username?: string; connection_id?: string };
      }>(this.topic)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((u) => {
        const pub = u.payload?._publisher;
        if (!pub?.connection_id) return;
        if (pub.username === this.myUsername && !this.myConnectionId) {
          this.myConnectionId = pub.connection_id;
        }
        if (pub.connection_id === this.myConnectionId) return;
        const next = new Map(this._peers());
        next.set(pub.connection_id, {
          username: pub.username || 'unknown',
          lastSeen: Date.now(),
          connectionId: pub.connection_id,
        });
        this._peers.set(next);
      });
  }

  /** Listen on the closest form element for input events. The
   *  component is typically dropped INSIDE a `<form>`, so the parent
   *  bubbles input events through us. */
  @HostListener('input')
  onParentInput(): void {
    if (!this.myUsername || !this.topic) return;
    const now = Date.now();
    if (now - this.lastSentAt < SEND_INTERVAL_MS) return;
    this.lastSentAt = now;
    this.realtime.publish(this.topic, 'typing', {
      username: this.myUsername,
    });
  }
}
