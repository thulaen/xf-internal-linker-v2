import { Component, Input, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-health-banner',
  standalone: true,
  imports: [RouterLink, MatButtonModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div [class]="'health-banner severity-' + severity" role="alert">
      <mat-icon class="banner-icon">{{ icon }}</mat-icon>
      <span class="banner-message">{{ message }}</span>
      @if (ctaLabel && ctaRoute) {
        <a mat-button [routerLink]="ctaRoute" class="banner-cta">{{ ctaLabel }}</a>
      }
    </div>
  `,
  styles: [`
    .health-banner {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-sm);
      font-size: 13px;
      width: 100%;
    }
    .banner-icon { font-size: 20px; width: 20px; height: 20px; flex-shrink: 0; }
    .banner-message { flex: 1; }
    .banner-cta { flex-shrink: 0; white-space: nowrap; }

    .severity-info {
      background: var(--color-blue-50);
      color: var(--color-primary);
    }
    .severity-info .banner-icon { color: var(--color-primary); }

    .severity-warning {
      background: var(--color-warning-light);
      color: var(--color-warning-dark);
    }
    .severity-warning .banner-icon { color: var(--color-warning); }

    .severity-error {
      background: var(--color-error-50);
      color: var(--color-error-dark);
    }
    .severity-error .banner-icon { color: var(--color-error); }
  `],
})
export class HealthBannerComponent {
  @Input({ required: true }) severity!: 'info' | 'warning' | 'error';
  @Input({ required: true }) message!: string;
  @Input() ctaLabel?: string;
  @Input() ctaRoute?: string;

  get icon(): string {
    switch (this.severity) {
      case 'info': return 'info';
      case 'warning': return 'warning';
      case 'error': return 'error';
    }
  }
}
