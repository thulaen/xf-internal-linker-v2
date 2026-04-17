import {
  ChangeDetectionStrategy,
  Component,
  Input,
  OnDestroy,
  OnInit,
  computed,
  inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

import { SoftLockService } from '../../../core/services/soft-lock.service';

/**
 * Phase RC / Gap 141 — Soft-lock banner.
 *
 * Drop above the editing surface for a record:
 *
 *   <app-soft-lock-banner targetType="suggestion" [targetId]="id" />
 *
 * The component claims the lock on init, releases on destroy, and
 * shows a yellow banner when SoftLockService reports another user
 * holding the same lock.
 *
 * Saving the form is NOT blocked — the banner just warns. If two
 * operators do save concurrently, last-write-wins. A future session
 * can promote this to hard-locking by adding a server-side optimistic
 * concurrency check; the UI contract stays the same.
 */
@Component({
  selector: 'app-soft-lock-banner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule],
  template: `
    @if (others().length > 0) {
      <aside class="slb" role="status" aria-live="polite">
        <mat-icon class="slb-icon" aria-hidden="true">edit_note</mat-icon>
        <span class="slb-text">
          @if (others().length === 1) {
            <strong>{{ others()[0].username }}</strong> is also editing this — your
            save will overwrite their changes (and vice versa).
          } @else {
            <strong>{{ others().length }} others</strong>
            ({{ usernameList() }}) are also editing this. Save with care.
          }
        </span>
      </aside>
    }
  `,
  styles: [`
    .slb {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      margin-bottom: 12px;
      background: var(--color-warning-light, rgba(249, 171, 0, 0.12));
      border: var(--card-border);
      border-left: 3px solid var(--color-warning, #f9ab00);
      border-radius: var(--card-border-radius, 8px);
      font-size: 13px;
      color: var(--color-warning-dark, #b06000);
    }
    .slb-icon { color: var(--color-warning, #f9ab00); }
    .slb-text strong { color: var(--color-text-primary); }
  `],
})
export class SoftLockBannerComponent implements OnInit, OnDestroy {
  @Input({ required: true }) targetType = '';
  @Input({ required: true }) targetId: string | number = '';

  private readonly lockSvc = inject(SoftLockService);

  readonly others = computed(() =>
    this.lockSvc.othersHolding(this.targetType, this.targetId),
  );

  readonly usernameList = computed(() =>
    this.others().map((o) => o.username).join(', '),
  );

  ngOnInit(): void {
    if (!this.targetType || !this.targetId) return;
    this.lockSvc.claim(this.targetType, this.targetId);
  }

  ngOnDestroy(): void {
    if (!this.targetType || !this.targetId) return;
    this.lockSvc.release(this.targetType, this.targetId);
  }
}
