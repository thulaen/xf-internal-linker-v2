import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatStepperModule } from '@angular/material/stepper';
import { Router } from '@angular/router';

@Component({
  selector: 'app-setup-wizard-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatStepperModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="icon-lg">rocket_launch</mat-icon>
      Welcome to XF Internal Linker
    </h2>

    <mat-dialog-content>
      <mat-stepper [linear]="false" #stepper>

        <!-- Step 1: Welcome -->
        <mat-step label="Welcome">
          <div class="wizard-step">
            <p class="wizard-lead">
              This app finds smart places to add internal links across your forum or blog.
            </p>
            <p>Here is how it works in four steps:</p>
            <ol class="wizard-steps-list">
              <li><strong>Connect</strong> your XenForo or WordPress site</li>
              <li><strong>Import</strong> your content so the system can read it</li>
              <li><strong>Run the pipeline</strong> to generate link suggestions</li>
              <li><strong>Review</strong> each suggestion and approve the good ones</li>
            </ol>
            <p class="wizard-note">The app never writes to your live site. You apply approved links yourself.</p>
            <div class="wizard-actions">
              <button mat-flat-button color="primary" matStepperNext>Get Started</button>
            </div>
          </div>
        </mat-step>

        <!-- Step 2: Connect -->
        <mat-step label="Connect">
          <div class="wizard-step">
            <p class="wizard-lead">Which platform does your content live on?</p>
            <div class="platform-buttons">
              <button mat-stroked-button class="platform-btn" (click)="goTo('/settings', 'xenforo-settings')">
                <mat-icon>forum</mat-icon>
                I use XenForo
              </button>
              <button mat-stroked-button class="platform-btn" (click)="goTo('/settings', 'wordpress-settings')">
                <mat-icon>description</mat-icon>
                I use WordPress
              </button>
            </div>
            <p class="wizard-hint">You can also import a .jsonl file if you prefer offline mode.</p>
            <div class="wizard-actions">
              <button mat-button matStepperPrevious>Back</button>
              <button mat-button matStepperNext>Skip</button>
            </div>
          </div>
        </mat-step>

        <!-- Step 3: Ready -->
        <mat-step label="Ready">
          <div class="wizard-step">
            <mat-icon class="wizard-done-icon">check_circle</mat-icon>
            <p class="wizard-lead">You are all set!</p>
            <p>After connecting, head to <strong>Jobs</strong> to import your content, then come back to the <strong>Dashboard</strong> to run the pipeline.</p>
            <div class="wizard-actions">
              <button mat-button matStepperPrevious>Back</button>
              <button mat-flat-button color="primary" (click)="goTo('/jobs')">Go to Jobs</button>
              <button mat-button mat-dialog-close>Stay on Dashboard</button>
            </div>
          </div>
        </mat-step>

      </mat-stepper>
    </mat-dialog-content>
  `,
  styles: [`
    :host {
      display: block;
    }

    h2[mat-dialog-title] {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 18px;
      font-weight: 500;

      .icon-lg {
        color: var(--color-primary);
      }
    }

    .wizard-step {
      padding: 16px 0;
    }

    .wizard-lead {
      font-size: 15px;
      font-weight: 500;
      color: var(--color-text-primary);
      margin-bottom: 12px;
    }

    .wizard-steps-list {
      padding-left: 24px;
      margin: 12px 0;
      line-height: 1.8;

      li {
        font-size: 13px;
        color: var(--color-text-secondary);
      }
    }

    .wizard-note {
      font-size: 12px;
      color: var(--color-text-muted);
      padding: 8px 12px;
      background: var(--color-bg-faint);
      border-radius: var(--card-border-radius);
    }

    .wizard-hint {
      font-size: 12px;
      color: var(--color-text-muted);
      margin-top: 16px;
    }

    .platform-buttons {
      display: flex;
      gap: 16px;
      margin: 16px 0;
    }

    .platform-btn {
      flex: 1;
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      border-radius: var(--card-border-radius);

      mat-icon {
        font-size: 32px;
        width: 32px;
        height: 32px;
        color: var(--color-primary);
      }
    }

    .wizard-done-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      color: var(--color-success);
      display: block;
      margin: 0 auto 12px;
    }

    .wizard-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 24px;
    }
  `],
})
export class SetupWizardDialogComponent {
  private dialogRef = inject(MatDialogRef<SetupWizardDialogComponent>);
  private router = inject(Router);

  goTo(route: string, fragment?: string): void {
    this.dialogRef.close();
    this.router.navigate([route], fragment ? { fragment } : {});
  }
}
