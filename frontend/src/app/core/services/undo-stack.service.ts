import { Injectable, computed, signal } from '@angular/core';

/**
 * Phase GK1 / Gap 214 — 5-deep undo stack.
 *
 * Extends the single-undo toast (Gap 31) with a history of up to 5
 * reversible actions. The Toast History drawer (Gap 213) renders the
 * list; each entry keeps a `reverse` closure that the user can fire by
 * clicking "Undo" in the drawer.
 *
 * Actions expire: each entry stores a TTL (default 10 min) and the
 * service purges on every `push` / `undo` call. Once an entry's
 * reverse fires, it is removed from the stack.
 */

export interface UndoAction {
  id: string;
  /** Short user-facing label ("Deleted suggestion #42"). */
  label: string;
  /** Monotonic createdAt — ms since epoch. */
  createdAt: number;
  /** Stack expires this entry at this timestamp. */
  expiresAt: number;
  /** Runs the compensating action. Must be idempotent. */
  reverse: () => Promise<void> | void;
  /** Free-form tag so the UI can filter / group. */
  tag?: string;
}

const MAX_ENTRIES = 5;
const DEFAULT_TTL_MS = 10 * 60 * 1000;

@Injectable({ providedIn: 'root' })
export class UndoStackService {
  private readonly _entries = signal<UndoAction[]>([]);

  /** Newest first. */
  readonly entries = computed(() => [...this._entries()].reverse());

  /** Newest entry, or null if the stack is empty. */
  readonly top = computed(() => this._entries()[this._entries().length - 1] ?? null);

  /** How many entries are currently undoable. */
  readonly count = computed(() => this._entries().length);

  push(
    label: string,
    reverse: () => Promise<void> | void,
    opts: { ttlMs?: number; tag?: string } = {},
  ): UndoAction {
    const now = Date.now();
    const entry: UndoAction = {
      id: `undo-${now}-${Math.random().toString(36).slice(2, 8)}`,
      label,
      createdAt: now,
      expiresAt: now + (opts.ttlMs ?? DEFAULT_TTL_MS),
      reverse,
      tag: opts.tag,
    };
    this.purgeExpired();
    const next = [...this._entries(), entry];
    // Trim to MAX_ENTRIES — oldest drops first.
    while (next.length > MAX_ENTRIES) next.shift();
    this._entries.set(next);
    return entry;
  }

  /** Undo the newest entry. Returns the entry that was undone, or null. */
  async undoTop(): Promise<UndoAction | null> {
    this.purgeExpired();
    const top = this._entries()[this._entries().length - 1];
    if (!top) return null;
    await this.runAndRemove(top);
    return top;
  }

  async undoById(id: string): Promise<UndoAction | null> {
    this.purgeExpired();
    const entry = this._entries().find((e) => e.id === id);
    if (!entry) return null;
    await this.runAndRemove(entry);
    return entry;
  }

  clear(): void {
    this._entries.set([]);
  }

  private async runAndRemove(entry: UndoAction): Promise<void> {
    try {
      await entry.reverse();
    } catch {
      // Swallow — we still remove the entry so the user isn't stuck
      // with a failed undo button that never goes away.
    }
    this._entries.set(this._entries().filter((e) => e.id !== entry.id));
  }

  private purgeExpired(): void {
    const now = Date.now();
    const next = this._entries().filter((e) => e.expiresAt > now);
    if (next.length !== this._entries().length) this._entries.set(next);
  }
}
