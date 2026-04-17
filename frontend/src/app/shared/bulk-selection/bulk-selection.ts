import { Injectable, computed, signal } from '@angular/core';

/**
 * Phase DC / Gap 120 — Per-table bulk selection state.
 *
 * Parent components new one of these per-table. The class tracks
 * which row ids are currently selected, exposes signals for
 * template bindings, and offers helpers for the three common
 * operations: toggle one, toggle all, clear.
 *
 * Why not @angular/cdk's SelectionModel: that's good, but its
 * observable-based API doesn't play well with Angular signals.
 * This is 50 lines and zero dependencies.
 */
@Injectable()
export class BulkSelection<Id = string> {
  private readonly _selected = signal<ReadonlySet<Id>>(new Set());
  /** Items currently present in the table — used by toggleAll. */
  private readonly _available = signal<readonly Id[]>([]);

  readonly selected = this._selected.asReadonly();

  readonly size = computed(() => this._selected().size);
  readonly isEmpty = computed(() => this._selected().size === 0);

  readonly allSelected = computed(() => {
    const s = this._selected();
    const avail = this._available();
    return avail.length > 0 && avail.every((id) => s.has(id));
  });

  readonly someSelected = computed(() => {
    const s = this._selected();
    return s.size > 0 && !this.allSelected();
  });

  /** Called by the parent every time the available list changes. */
  syncAvailable(ids: readonly Id[]): void {
    this._available.set([...ids]);
    // Drop selections that no longer correspond to a visible row.
    const set = new Set(ids);
    const s = this._selected();
    let changed = false;
    const next = new Set<Id>();
    for (const id of s) {
      if (set.has(id)) next.add(id);
      else changed = true;
    }
    if (changed) this._selected.set(next);
  }

  isSelected(id: Id): boolean {
    return this._selected().has(id);
  }

  toggle(id: Id): void {
    const next = new Set(this._selected());
    if (next.has(id)) next.delete(id);
    else next.add(id);
    this._selected.set(next);
  }

  toggleAll(): void {
    if (this.allSelected()) {
      this.clear();
    } else {
      this._selected.set(new Set(this._available()));
    }
  }

  clear(): void {
    this._selected.set(new Set());
  }

  /** Snapshot the selected ids for an action. */
  ids(): Id[] {
    return [...this._selected()];
  }
}
