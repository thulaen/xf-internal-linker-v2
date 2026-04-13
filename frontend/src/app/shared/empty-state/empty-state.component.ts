import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [RouterLink, MatButtonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty-state">
      <mat-icon class="empty-icon">{{ icon }}</mat-icon>
      <h3 class="empty-heading">{{ heading }}</h3>
      <p class="empty-body">{{ body }}</p>
      @if (example) {
        <p class="empty-example">{{ example }}</p>
      }
      @if (ctaLabel && ctaRoute) {
        <a mat-raised-button color="primary" [routerLink]="ctaRoute" class="empty-cta">
          {{ ctaLabel }}
        </a>
      }
    </div>
  `,
  styles: [`
    .empty-state {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 48px 24px;
      min-height: 200px;
    }
    .empty-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      color: var(--color-text-muted);
      margin-bottom: var(--space-md);
    }
    .empty-heading {
      font-size: 16px;
      font-weight: 500;
      color: var(--color-text-primary);
      margin: 0 0 var(--space-sm);
    }
    .empty-body {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 var(--space-md);
      max-width: 400px;
    }
    .empty-example {
      font-size: 12px;
      color: var(--color-text-muted);
      font-style: italic;
      margin: 0 0 var(--space-md);
    }
    .empty-cta { margin-top: var(--space-sm); }
  `],
})
export class EmptyStateComponent {
  @Input({ required: true }) icon!: string;
  @Input({ required: true }) heading!: string;
  @Input({ required: true }) body!: string;
  @Input() example?: string;
  @Input() ctaLabel?: string;
  @Input() ctaRoute?: string;
}
