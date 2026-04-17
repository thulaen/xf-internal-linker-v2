import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { Router, NavigationEnd, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { filter } from 'rxjs';

/**
 * Phase D2 / Gap 74 — "Take me back to safe ground" Escape Hatch FAB.
 *
 * A floating button anchored to the bottom-left of every page EXCEPT
 * the dashboard itself. Clicking it navigates to /dashboard. Useful
 * for noobs who get lost in deep pages and don't know how to get back
 * to a known-good starting point.
 *
 * Hidden on:
 *   - The dashboard (no point linking to where you already are).
 *   - The login page (auth-only navigation hasn't kicked in yet).
 *
 * The Esc key is ALSO bound to "go to dashboard" — but only when no
 * dialog or input is focused, to avoid stealing keystrokes from
 * forms / dialogs / cdk-overlay listeners.
 */
@Component({
  selector: 'app-escape-hatch',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
  ],
  template: `
    @if (visible()) {
      <a
        mat-fab
        extended
        class="eh-fab"
        color="primary"
        routerLink="/dashboard"
        matTooltip="Take me back to the dashboard (Esc on most pages)"
        matTooltipPosition="right"
        aria-label="Return to dashboard"
      >
        <mat-icon>home</mat-icon>
        Safe ground
      </a>
    }
  `,
  styles: [`
    .eh-fab {
      position: fixed;
      bottom: 24px;
      left: 24px;
      z-index: 980;
      box-shadow: var(--shadow-md, 0 2px 6px rgba(60, 64, 67, 0.15));
      transition: transform 0.2s ease;
    }
    .eh-fab:hover {
      transform: translateY(-2px);
    }
    @media (prefers-reduced-motion: reduce) {
      .eh-fab { transition: none; }
    }
    @media (max-width: 480px) {
      .eh-fab {
        bottom: 16px;
        left: 16px;
      }
    }
  `],
})
export class EscapeHatchComponent implements OnInit {
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly visible = signal(false);

  ngOnInit(): void {
    this.visible.set(this.shouldShow(this.router.url));
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => {
        const url = (e as NavigationEnd).urlAfterRedirects;
        this.visible.set(this.shouldShow(url));
      });
  }

  /** Esc shortcut — only when no input/dialog has focus. */
  @HostListener('document:keydown.escape', ['$event'])
  onEsc(event: KeyboardEvent): void {
    if (!this.visible()) return;
    const target = event.target as HTMLElement | null;
    if (!target) {
      this.router.navigate(['/dashboard']);
      return;
    }
    const tag = target.tagName.toLowerCase();
    const editable = target.isContentEditable;
    // Don't steal Esc from form fields or dialog overlays.
    if (
      tag === 'input' ||
      tag === 'textarea' ||
      tag === 'select' ||
      editable ||
      target.closest('[role="dialog"]') ||
      target.closest('.cdk-overlay-container')
    ) {
      return;
    }
    event.preventDefault();
    this.router.navigate(['/dashboard']);
  }

  private shouldShow(url: string): boolean {
    const noQs = (url ?? '').split('?')[0].split('#')[0];
    if (noQs === '/' || noQs.startsWith('/dashboard')) return false;
    if (noQs.startsWith('/login')) return false;
    return true;
  }
}
