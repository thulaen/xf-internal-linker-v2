import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase U1 / Gap 18 — Dedicated 500 / "something went wrong" page.
 *
 * The Global ErrorHandler (Gap 26) routes unrecoverable Angular errors
 * here so the user lands on a helpful page instead of a blank screen.
 * Visual style mirrors the 404 page for consistency.
 */
@Component({
  selector: 'app-server-error',
  standalone: true,
  // Phase E1 / Gap 28 — static page with no inputs or subscriptions.
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, MatButtonModule, MatIconModule],
  template: `
    <div class="server-error-container" role="alert">
      <mat-icon class="server-error-icon" aria-hidden="true">sentiment_very_dissatisfied</mat-icon>
      <h1 class="server-error-title">Something went wrong</h1>
      <p class="server-error-body">
        An unexpected error stopped the page from loading. The issue has
        been reported — you can try again or head back to the dashboard.
      </p>
      <div class="server-error-actions">
        <button mat-stroked-button type="button" (click)="onReload()">
          <mat-icon>refresh</mat-icon>
          Try again
        </button>
        <a mat-raised-button color="primary" routerLink="/dashboard">
          Go to Dashboard
        </a>
      </div>
    </div>
  `,
  styles: [`
    .server-error-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 60vh;
      text-align: center;
      padding: 48px 24px;
    }
    .server-error-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      color: var(--color-error);
      margin-bottom: 16px;
    }
    .server-error-title {
      font-size: 22px;
      font-weight: 500;
      color: var(--color-text-primary);
      margin: 0 0 8px;
    }
    .server-error-body {
      font-size: 13px;
      color: var(--color-text-secondary);
      margin: 0 0 24px;
      max-width: 480px;
    }
    .server-error-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: center;
    }
    .server-error-actions mat-icon {
      margin-right: 4px;
    }
  `],
})
export class ServerErrorComponent {
  /**
   * Try-again reloads the whole app rather than retrying a specific
   * request — by the time we're here, Angular's state is suspect
   * enough that a clean reload is safer than in-place retry.
   */
  onReload(): void {
    window.location.reload();
  }
}
