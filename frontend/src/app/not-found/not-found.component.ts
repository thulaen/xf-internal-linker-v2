import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-not-found',
  standalone: true,
  // Phase E1 / Gap 28 — static page with no inputs or subscriptions.
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, MatIconModule],
  template: `
    <div class="not-found-container">
      <mat-icon class="not-found-icon">search_off</mat-icon>
      <h1 class="not-found-title">Page not found</h1>
      <p class="not-found-body">The page you're looking for doesn't exist or has been moved.</p>
      <a mat-raised-button color="primary" routerLink="/dashboard">Go to Dashboard</a>
    </div>
  `,
  styles: [`
    .not-found-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 60vh;
      text-align: center;
      padding: 48px 24px;
    }
    .not-found-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      color: var(--color-text-secondary);
      margin-bottom: 16px;
    }
    .not-found-title {
      font-size: 22px;
      font-weight: 500;
      color: var(--color-text-primary);
      margin: 0 0 8px;
    }
    .not-found-body {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 24px;
    }
  `],
})
export class NotFoundComponent {}
