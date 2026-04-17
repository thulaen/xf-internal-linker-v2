import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase D1 / Gap 59 — Color Legend card.
 *
 * A persistent tiny reference card showing what each status color means
 * in this app. The GA4 visual identity uses green/amber/red/blue in
 * dozens of places; noobs need one obvious place to look them up.
 *
 * Static content — no data fetch, no state, no inputs. This is
 * deliberately dumb so the semantics never drift from what the rest of
 * the app uses.
 */
@Component({
  selector: 'app-color-legend',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatCardModule, MatIconModule],
  template: `
    <mat-card class="cl-card">
      <mat-card-header>
        <mat-icon mat-card-avatar class="cl-avatar">palette</mat-icon>
        <mat-card-title>Color key</mat-card-title>
        <mat-card-subtitle>What the dots and chips mean</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <dl class="cl-grid">
          <div class="cl-row">
            <span class="cl-swatch cl-swatch-success" aria-hidden="true"></span>
            <dt>Green</dt>
            <dd>Healthy / success / no action needed.</dd>
          </div>
          <div class="cl-row">
            <span class="cl-swatch cl-swatch-warning" aria-hidden="true"></span>
            <dt>Amber</dt>
            <dd>Warning — degraded but still working. Check soon.</dd>
          </div>
          <div class="cl-row">
            <span class="cl-swatch cl-swatch-error" aria-hidden="true"></span>
            <dt>Red</dt>
            <dd>Broken / urgent. Needs attention now.</dd>
          </div>
          <div class="cl-row">
            <span class="cl-swatch cl-swatch-primary" aria-hidden="true"></span>
            <dt>Blue</dt>
            <dd>Informational — an action button or a neutral metric.</dd>
          </div>
          <div class="cl-row">
            <span class="cl-swatch cl-swatch-muted" aria-hidden="true"></span>
            <dt>Grey</dt>
            <dd>Idle / not configured / not yet run.</dd>
          </div>
        </dl>
      </mat-card-content>
    </mat-card>
  `,
  styles: [`
    .cl-card { height: 100%; }
    .cl-avatar {
      background: var(--color-primary);
      color: var(--color-on-primary, #ffffff);
    }
    .cl-grid {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 0;
    }
    .cl-row {
      display: grid;
      grid-template-columns: 20px 56px 1fr;
      gap: 12px;
      align-items: baseline;
    }
    .cl-swatch {
      display: inline-block;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      margin-top: 2px;
      border: 1px solid rgba(0, 0, 0, 0.1);
    }
    .cl-swatch-success { background: var(--color-success, #1e8e3e); }
    .cl-swatch-warning { background: var(--color-warning, #f9ab00); }
    .cl-swatch-error   { background: var(--color-error, #d93025); }
    .cl-swatch-primary { background: var(--color-primary, #1a73e8); }
    .cl-swatch-muted   { background: var(--color-text-disabled, #bdc1c6); }
    dt {
      font-weight: 500;
      font-size: 12px;
      color: var(--color-text-primary);
      margin: 0;
    }
    dd {
      font-size: 12px;
      color: var(--color-text-secondary);
      line-height: 1.4;
      margin: 0;
    }
  `],
})
export class ColorLegendComponent {}
