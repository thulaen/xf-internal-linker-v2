import {
  AfterViewInit,
  Directive,
  Host,
  inject,
  Input,
  OnDestroy,
  OnInit,
  Optional,
} from '@angular/core';
import { MatTabGroup } from '@angular/material/tabs';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { TabPersistenceService } from '../services/tab-persistence.service';

/**
 * Phase NV / Gap 145 — Tab groups persistence directive.
 *
 * Drop on any `<mat-tab-group appPersistTab="settings.general">` to
 * have the active tab index restored on the next page visit.
 *
 * Behavior:
 *   • On view init, restore the last-saved index (if any) onto the host
 *     MatTabGroup. Wrapped in queueMicrotask so it doesn't fight Angular's
 *     own initial selection.
 *   • Subscribes to `selectedIndexChange` and writes through to localStorage
 *     on every user-driven change.
 *   • If the host isn't a MatTabGroup it logs a warning and no-ops; the
 *     surrounding template won't crash.
 */
@Directive({
  selector: 'mat-tab-group[appPersistTab]',
  standalone: true,
})
export class PersistTabDirective implements OnInit, AfterViewInit, OnDestroy {
  @Input('appPersistTab') id = '';

  private store = inject(TabPersistenceService);
  private destroy$ = new Subject<void>();

  constructor(@Host() @Optional() private host: MatTabGroup | null) {}

  ngOnInit(): void {
    if (!this.host) {
      console.warn('[appPersistTab] host is not a MatTabGroup — directive is a no-op.');
      return;
    }
    if (!this.id) {
      console.warn('[appPersistTab] missing storage id — directive is a no-op.');
      return;
    }
    this.host.selectedIndexChange
      .pipe(takeUntil(this.destroy$))
      .subscribe((idx) => this.store.write(this.id, idx));
  }

  ngAfterViewInit(): void {
    if (!this.host || !this.id) return;
    const stored = this.store.read(this.id, this.host.selectedIndex ?? 0);
    if (stored === this.host.selectedIndex) return;
    // queueMicrotask so we apply after Angular's own change-detection cycle
    // for the initial selectedIndex binding.
    queueMicrotask(() => {
      if (!this.host) return;
      // Clamp against the actual tab count to survive removed/reordered tabs.
      const max = (this.host._tabs?.length ?? 0) - 1;
      this.host.selectedIndex = Math.min(stored, Math.max(0, max));
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
