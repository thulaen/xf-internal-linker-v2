import { Injectable, computed, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';

/**
 * Phase GK1 / Gap 197 — Recent actions history drawer.
 *
 * In-memory-plus-localStorage ring buffer of the last 50 operator
 * actions (approvals, rejections, setting changes, bulk deletes).
 * Powers the "Things you did today" drawer and also feeds Gap 195
 * "Undo everything from this session".
 *
 * Distinct from the Undo Stack (Gap 214): undo is a 5-deep stack of
 * reversible operations keyed by reverse closures. This service is
 * a longer, read-only log — great for audit ("what did I do today")
 * but it doesn't own reverse closures.
 */

export interface RecordedAction {
  id: string;
  /** Short imperative sentence ("Approved suggestion #42"). */
  label: string;
  /** Free-form category so the drawer can colour the row. */
  category: 'approve' | 'reject' | 'settings' | 'delete' | 'export' | 'other';
  /** When the action fired (Unix ms). */
  at: number;
  /** Optional detail used to reconstruct the action target. */
  target?: { type: string; id: string | number };
}

const STORAGE_KEY = 'actionsh.v1';
const MAX = 50;

@Injectable({ providedIn: 'root' })
export class ActionsHistoryService {
  private doc = inject(DOCUMENT);

  private readonly _entries = signal<RecordedAction[]>(this.load());

  readonly entries = computed(() => this._entries());
  readonly today = computed(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return this._entries().filter((e) => e.at >= start.getTime());
  });

  record(entry: Omit<RecordedAction, 'id' | 'at'> & { at?: number }): RecordedAction {
    const saved: RecordedAction = {
      id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      at: entry.at ?? Date.now(),
      label: entry.label,
      category: entry.category,
      target: entry.target,
    };
    const next = [saved, ...this._entries()].slice(0, MAX);
    this._entries.set(next);
    this.persist();
    return saved;
  }

  clear(): void {
    this._entries.set([]);
    this.persist();
  }

  private persist(): void {
    try {
      this.doc.defaultView?.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(this._entries()),
      );
    } catch {
      /* ignore */
    }
  }

  private load(): RecordedAction[] {
    try {
      const raw = this.doc.defaultView?.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .filter(
          (e): e is RecordedAction =>
            !!e &&
            typeof e === 'object' &&
            typeof (e as RecordedAction).label === 'string' &&
            typeof (e as RecordedAction).at === 'number',
        )
        .slice(0, MAX);
    } catch {
      return [];
    }
  }
}
