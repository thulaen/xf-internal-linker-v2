import { Injectable, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Observable, Subject, share } from 'rxjs';

/**
 * Phase GK2 / Gap 247 — BroadcastChannel cross-tab sync.
 *
 * One operator commonly opens the app in multiple tabs (one for the
 * dashboard, one for Review). When they approve a suggestion in tab A
 * it should reflect in tab B without a refresh. This service wraps
 * `BroadcastChannel` so callers don't have to remember the channel
 * name or handle browsers without API support.
 *
 * Usage:
 *   // emitter
 *   sync.emit({ kind: 'suggestion.approved', id: 42 });
 *   // listener
 *   sync.messages$.subscribe(msg => {
 *     if (msg.kind === 'suggestion.approved') refresh();
 *   });
 *
 * Same-tab messages are NOT echoed back — each listener sees only
 * events from OTHER tabs, matching native BroadcastChannel semantics.
 */

export interface CrossTabMessage {
  kind: string;
  /** Unix ms at the sender. */
  at: number;
  payload?: unknown;
}

const CHANNEL_NAME = 'xfil.crosstab.v1';

@Injectable({ providedIn: 'root' })
export class CrossTabSyncService {
  private doc = inject(DOCUMENT);

  private channel: BroadcastChannel | null = null;
  private readonly _messages$ = new Subject<CrossTabMessage>();
  /** Shared observable — all subscribers get the same underlying BC stream. */
  readonly messages$: Observable<CrossTabMessage> = this._messages$.pipe(share());

  constructor() {
    const w = this.doc.defaultView;
    if (!w || typeof (w as unknown as { BroadcastChannel?: unknown }).BroadcastChannel === 'undefined') {
      return; // Safari < 15.4 and some embedded browsers lack BC.
    }
    try {
      this.channel = new BroadcastChannel(CHANNEL_NAME);
      this.channel.onmessage = (ev: MessageEvent<CrossTabMessage>) => {
        const data = ev.data;
        if (!data || typeof data !== 'object' || !('kind' in data)) return;
        this._messages$.next(data as CrossTabMessage);
      };
    } catch {
      /* constructor can throw in cross-origin iframes */
      this.channel = null;
    }
  }

  emit(kind: string, payload?: unknown): void {
    if (!this.channel) return;
    try {
      this.channel.postMessage({ kind, at: Date.now(), payload });
    } catch {
      /* messaging can fail if the tab just went into bfcache */
    }
  }
}
