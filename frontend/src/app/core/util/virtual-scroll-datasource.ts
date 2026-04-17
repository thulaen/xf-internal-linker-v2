import { CollectionViewer, DataSource } from '@angular/cdk/collections';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';

/**
 * Phase E1 / Gap 27 — VirtualScrollDataSource<T>
 *
 * A CDK DataSource implementation that wraps a plain array and works with:
 *   - `cdk-virtual-scroll-viewport` + `*cdkVirtualFor`
 *   - `mat-table` when combined with virtual scroll
 *
 * Usage with cdk-virtual-scroll-viewport:
 *
 *   // In component:
 *   dataSource = new VirtualScrollDataSource(this.items);
 *
 *   // Update items reactively:
 *   this.dataSource.setData(newItems);
 *
 *   // Template:
 *   <cdk-virtual-scroll-viewport itemSize="48" class="viewport">
 *     <div *cdkVirtualFor="let item of dataSource; trackBy: trackById">
 *       {{ item.name }}
 *     </div>
 *   </cdk-virtual-scroll-viewport>
 *
 * Usage with mat-table + virtual scroll:
 *   Pass as [dataSource] to mat-table. The table must be inside
 *   cdk-virtual-scroll-viewport with a fixed itemSize matching row height.
 *
 * Design notes:
 *   - itemSize should match the CSS `height` of each row (px). For mat-table
 *     rows the default is 48px (CLAUDE.md component rules).
 *   - The viewport height should be capped (e.g. max-height: 600px) in CSS
 *     so the scroll region is visible. An uncapped viewport would make the
 *     entire page scroll instead.
 */
export class VirtualScrollDataSource<T> extends DataSource<T> {
  private readonly data$ = new BehaviorSubject<T[]>([]);
  private sub: Subscription | null = null;

  constructor(initialData: T[] = []) {
    super();
    this.data$.next(initialData);
  }

  /** Replace the entire dataset. Triggers re-render. */
  setData(data: T[]): void {
    this.data$.next(data);
  }

  /** Current dataset snapshot. */
  get data(): T[] {
    return this.data$.value;
  }

  /** Total item count — required by cdk-virtual-scroll-viewport to calculate scroll height. */
  get length(): number {
    return this.data$.value.length;
  }

  // DataSource contract ──────────────────────────────────────────────

  connect(viewer: CollectionViewer): Observable<T[]> {
    void viewer; // CollectionViewer param required by CDK interface
    // We push ALL data on every change. For very large sets (>10 000 rows)
    // switch to a windowed observable using `viewer.viewChange`. For the
    // typical use-case of a few hundred rows, pushing everything is simpler
    // and cheaper than the windowing overhead.
    return this.data$.asObservable();
  }

  disconnect(viewer: CollectionViewer): void {
    void viewer;
    this.sub?.unsubscribe();
    this.sub = null;
  }
}
