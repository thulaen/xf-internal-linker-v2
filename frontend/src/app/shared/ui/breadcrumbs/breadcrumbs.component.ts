import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { BreadcrumbService } from '../../../core/services/breadcrumb.service';

/**
 * Phase NV / Gap 143 — Breadcrumb trail.
 *
 * Renders the current route's ancestry as a horizontal list of links,
 * with a chevron between each crumb and the current page rendered as
 * plain text (no link). Hidden by default — only renders when the
 * BreadcrumbService reports depth ≥3.
 *
 * Accessibility: wrapped in <nav aria-label="Breadcrumb"> with the
 * trailing crumb marked aria-current="page" per WAI-ARIA breadcrumbs
 * pattern.
 */
@Component({
  selector: 'app-breadcrumbs',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, RouterLink, MatIconModule],
  template: `
    @if (svc.visible()) {
      <nav class="bc-bar" aria-label="Breadcrumb">
        <ol class="bc-list">
          @for (c of svc.crumbs(); track c.url; let last = $last) {
            <li class="bc-item">
              @if (c.current) {
                <span class="bc-current" aria-current="page">{{ c.label }}</span>
              } @else {
                <a class="bc-link" [routerLink]="c.url">{{ c.label }}</a>
              }
              @if (!last) {
                <mat-icon class="bc-sep" aria-hidden="true">chevron_right</mat-icon>
              }
            </li>
          }
        </ol>
      </nav>
    }
  `,
  styles: [`
    .bc-bar {
      padding: 8px 24px;
      background: var(--color-bg-faint, #f8f9fa);
      border-bottom: 0.8px solid var(--color-border, #dadce0);
    }
    .bc-list {
      display: flex;
      align-items: center;
      gap: 4px;
      list-style: none;
      margin: 0;
      padding: 0;
      flex-wrap: wrap;
      font-size: 13px;
    }
    .bc-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .bc-link {
      color: var(--color-primary, #1a73e8);
      text-decoration: none;
      padding: 2px 4px;
      border-radius: 4px;
    }
    .bc-link:hover { text-decoration: underline; }
    .bc-link:focus-visible {
      outline: 2px solid var(--color-primary, #1a73e8);
      outline-offset: 2px;
    }
    .bc-current {
      color: var(--color-text-primary, #202124);
      font-weight: 500;
    }
    .bc-sep {
      width: 16px;
      height: 16px;
      font-size: 16px;
      color: var(--color-text-secondary, #5f6368);
    }
  `],
})
export class BreadcrumbsComponent {
  protected svc = inject(BreadcrumbService);
}
