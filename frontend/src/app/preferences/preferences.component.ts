import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { A11yPrefsService } from '../core/services/a11y-prefs.service';
import { LocaleService } from '../core/services/locale.service';
import { NoobModeService } from '../core/services/noob-mode.service';
import { TutorialModeService } from '../core/services/tutorial-mode.service';
import { ExplainModeService } from '../core/services/explain-mode.service';
import { RecentPagesService } from '../core/services/recent-pages.service';
import { TabPersistenceService } from '../core/services/tab-persistence.service';
import {
  ONBOARDING_CATALOGUE,
  OnboardingStateService,
} from '../core/services/onboarding-state.service';
import { FeatureRequestDialogComponent } from '../shared/ui/feature-request-dialog/feature-request-dialog.component';
import {
  PasskeyCredentialSummary,
  PasskeyService,
} from '../core/services/passkey.service';

/**
 * Phase GB / Gap 149 — User Preference Center.
 *
 * Consolidates every client-side preference under one roof so an
 * operator can find and reset them without hunting across pages. No
 * new state added — every section delegates to its existing service,
 * so changes here instantly propagate to the rest of the app.
 *
 * Sections:
 *   1. Appearance       — density, contrast, font size, dyslexia font
 *   2. Colour-vision    — protan / deutan / tritan palettes
 *   3. Accessibility    — motion, noob/pro mode (advanced knobs)
 *   4. Language & time  — locale + timezone + currency
 *   5. Behavior         — tutorial / explain modes
 *   6. Onboarding       — re-run tours + progress meter (Gap 150)
 *   7. Data hygiene     — clear recent pages + tab prefs
 *   8. Feedback         — open the Suggest-a-Feature dialog (Gap 151)
 *
 * Every toggle / dropdown updates its service synchronously and
 * persists via the service's own localStorage. No dedicated save
 * button — UX matches macOS System Settings / Android Settings.
 */
@Component({
  selector: 'app-preferences',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatDialogModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatListModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  template: `
    <div class="pc-page">
      <header class="pc-header">
        <h1 class="pc-title">
          <mat-icon>tune</mat-icon>
          Preferences
        </h1>
        <p class="pc-subtitle">
          One place for every client-side setting. Changes save automatically.
        </p>
      </header>

      <!-- 1. Appearance ──────────────────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Appearance</mat-card-title>
          <mat-card-subtitle>
            Contrast, font family, and font size.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content class="pc-grid">
          <div class="pc-row">
            <label>High contrast</label>
            <mat-slide-toggle
              [checked]="a11y.contrast() === 'high'"
              (change)="a11y.setContrast($event.checked ? 'high' : 'normal')"
            />
          </div>
          <div class="pc-row">
            <label>Dyslexia-friendly font</label>
            <mat-slide-toggle
              [checked]="a11y.fontStack() === 'dyslexia'"
              (change)="a11y.setFontStack($event.checked ? 'dyslexia' : 'system')"
            />
          </div>
          <div class="pc-row">
            <label>Font size</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <mat-select
                [value]="a11y.fontSize()"
                (valueChange)="a11y.setFontSize($event)"
              >
                <mat-option [value]="90">90% — compact</mat-option>
                <mat-option [value]="100">100% — default</mat-option>
                <mat-option [value]="115">115% — comfortable</mat-option>
                <mat-option [value]="130">130% — large</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
        </mat-card-content>
      </mat-card>

      <!-- 2. Colour-vision palette ─────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Colour-vision palette</mat-card-title>
          <mat-card-subtitle>
            Switch to a palette safer for protanopia, deuteranopia, or tritanopia.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="pc-row">
            <label>Palette</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <mat-select
                [value]="a11y.cvdPalette()"
                (valueChange)="a11y.setCvdPalette($event)"
              >
                <mat-option value="none">Off (default)</mat-option>
                <mat-option value="protanopia">Protanopia (red-weak)</mat-option>
                <mat-option value="deuteranopia">Deuteranopia (green-weak)</mat-option>
                <mat-option value="tritanopia">Tritanopia (blue-weak)</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
        </mat-card-content>
      </mat-card>

      <!-- 3. Interface mode ───────────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Interface mode</mat-card-title>
          <mat-card-subtitle>
            Start simple, reveal advanced controls only when you need them.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="pc-row">
            <label>Operator mode</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <mat-select
                [value]="noob.mode()"
                (valueChange)="noob.setMode($event)"
              >
                <mat-option value="noob">Noob — hide advanced knobs</mat-option>
                <mat-option value="pro">Pro — show everything</mat-option>
              </mat-select>
            </mat-form-field>
          </div>
        </mat-card-content>
      </mat-card>

      <!-- 4. Language / time ──────────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Language, timezone, and currency</mat-card-title>
          <mat-card-subtitle>
            Every number, date, and price renders in your preferred format.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content class="pc-grid">
          <div class="pc-row">
            <label>Language (locale)</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <input
                matInput
                autocomplete="off"
                [value]="locale.locale()"
                (change)="onLocaleChange($event)"
                placeholder="en-US"
              />
            </mat-form-field>
          </div>
          <div class="pc-row">
            <label>Timezone (IANA)</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <input
                matInput
                autocomplete="off"
                [value]="locale.timezone()"
                (change)="onTimezoneChange($event)"
                placeholder="America/New_York"
              />
            </mat-form-field>
          </div>
          <div class="pc-row">
            <label>Currency (ISO 4217)</label>
            <mat-form-field appearance="outline" class="pc-inline-field">
              <input
                matInput
                autocomplete="off"
                [value]="locale.currency()"
                (change)="onCurrencyChange($event)"
                placeholder="USD"
              />
            </mat-form-field>
          </div>
        </mat-card-content>
      </mat-card>

      <!-- 5. Behavior toggles ─────────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Guidance &amp; explanations</mat-card-title>
          <mat-card-subtitle>
            Show learning helpers or hide them once you know the app.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content class="pc-grid">
          <div class="pc-row">
            <label>
              Tutorial hints
              <span class="pc-hint">Callouts on each dashboard card.</span>
            </label>
            <mat-slide-toggle
              [checked]="tutorial.enabled()"
              (change)="tutorial.setEnabled($event.checked)"
            />
          </div>
          <div class="pc-row">
            <label>
              Explain mode
              <span class="pc-hint">Info icons next to every widget.</span>
            </label>
            <mat-slide-toggle
              [checked]="explain.enabled()"
              (change)="explain.setEnabled($event.checked)"
            />
          </div>
        </mat-card-content>
        <mat-card-actions>
          <button
            mat-stroked-button
            type="button"
            (click)="tutorial.resetDismissals()"
          >
            <mat-icon>refresh</mat-icon>
            Show all hints again
          </button>
        </mat-card-actions>
      </mat-card>

      <!-- 6. Onboarding (Gap 150) ────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Onboarding progress</mat-card-title>
          <mat-card-subtitle>
            Re-run any tour or reset everything so it shows from scratch.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="pc-progress">
            <div class="pc-progress-label">
              <span>{{ onboarding.progress().done }}
                of {{ onboarding.progress().total }} milestones completed</span>
              <span>{{ onboarding.progress().percent }}%</span>
            </div>
            <mat-progress-bar
              mode="determinate"
              [value]="onboarding.progress().percent"
            />
          </div>
          <ul class="pc-milestones">
            @for (id of catalogue; track id) {
              <li>
                @if (onboarding.isDone(id)) {
                  <mat-icon class="pc-done">check_circle</mat-icon>
                } @else {
                  <mat-icon class="pc-pending">radio_button_unchecked</mat-icon>
                }
                <span class="pc-ms-label">{{ prettifyMilestone(id) }}</span>
                @if (onboarding.isDone(id)) {
                  <button
                    mat-button
                    type="button"
                    color="primary"
                    (click)="onboarding.reset(id)"
                  >
                    Show again
                  </button>
                }
              </li>
            }
          </ul>
        </mat-card-content>
        <mat-card-actions>
          <button
            mat-stroked-button
            type="button"
            (click)="confirmAndResetOnboarding()"
          >
            <mat-icon>restart_alt</mat-icon>
            Restart all onboarding
          </button>
        </mat-card-actions>
      </mat-card>

      <!-- 7. Data hygiene ────────────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Stored UI state</mat-card-title>
          <mat-card-subtitle>
            Clear remembered things when this browser doesn't feel like yours.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <div class="pc-row pc-row-multi">
            <button mat-stroked-button type="button" (click)="clearRecentPages()">
              <mat-icon>delete_outline</mat-icon>
              Clear recent-pages history
            </button>
            <button mat-stroked-button type="button" (click)="clearTabPrefs()">
              <mat-icon>tab</mat-icon>
              Reset remembered tab positions
            </button>
            <button mat-stroked-button type="button" (click)="resetA11yPrefs()">
              <mat-icon>accessibility_new</mat-icon>
              Reset accessibility prefs
            </button>
          </div>
        </mat-card-content>
      </mat-card>

      <!-- 8. Feedback (Gap 151) ───────────────────────────── -->
      <mat-card class="pc-card">
        <mat-card-header>
          <mat-card-title>Suggest a feature</mat-card-title>
          <mat-card-subtitle>
            Tell us what to build next. Your submissions land in the
            maintainer queue.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-actions>
          <button
            mat-raised-button
            color="primary"
            type="button"
            (click)="openFeatureRequestDialog()"
          >
            <mat-icon>lightbulb</mat-icon>
            Open feature-request form
          </button>
        </mat-card-actions>
      </mat-card>

      <!-- 9. Passkeys ─────────────────────────────────────── -->
      <mat-card class="pc-card" id="passkeys">
        <mat-card-header>
          <mat-card-title>Passkeys</mat-card-title>
          <mat-card-subtitle>
            Sign in with your fingerprint, face, or hardware key — no password
            needed. A passkey is a small key your browser stores in your
            laptop's secure chip; we never see it. The site asks "is the same
            person here?" and your laptop answers yes.
          </mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          @if (passkeysLoading()) {
            <div class="pk-loading">
              <mat-spinner diameter="24"></mat-spinner>
              <span>Loading your passkeys…</span>
            </div>
          } @else if (passkeyError()) {
            <p class="pk-error">{{ passkeyError() }}</p>
          } @else if (passkeys().length === 0) {
            <p class="pk-empty">
              You haven't added any passkeys yet. Click "Add a passkey" below
              to enrol the device you're on now.
            </p>
          } @else {
            <mat-list class="pk-list">
              @for (k of passkeys(); track k.id) {
                <mat-list-item class="pk-row">
                  <mat-icon matListItemIcon>vpn_key</mat-icon>
                  <div matListItemTitle>{{ k.label || 'Unnamed passkey' }}</div>
                  <div matListItemLine class="pk-meta">
                    @if (k.transports.length > 0) {
                      <span>{{ k.transports.join(' · ') }}</span>
                      <span>·</span>
                    }
                    <span>
                      @if (k.last_used_at) {
                        Last used {{ formatRelative(k.last_used_at) }}
                      } @else {
                        Never used yet
                      }
                    </span>
                  </div>
                  <button
                    mat-icon-button
                    matListItemMeta
                    type="button"
                    matTooltip="Rename this passkey"
                    (click)="renamePasskey(k)"
                  >
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button
                    mat-icon-button
                    matListItemMeta
                    type="button"
                    matTooltip="Delete this passkey"
                    (click)="deletePasskey(k)"
                  >
                    <mat-icon>delete</mat-icon>
                  </button>
                </mat-list-item>
              }
            </mat-list>
          }
        </mat-card-content>
        <mat-card-actions>
          <button
            mat-raised-button
            color="primary"
            type="button"
            [disabled]="passkeyBusy() || !passkeySupported"
            (click)="addPasskey()"
          >
            @if (passkeyBusy()) {
              <mat-spinner diameter="18" class="btn-spinner"></mat-spinner>
            } @else {
              <mat-icon>fingerprint</mat-icon>
            }
            Add a passkey
          </button>
          @if (!passkeySupported) {
            <span class="pk-unsupported">
              Your browser doesn't support passkeys.
            </span>
          }
        </mat-card-actions>
      </mat-card>
    </div>
  `,
  styles: [`
    .pc-page {
      max-width: 840px;
      margin: 0 auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    .pc-header {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .pc-title {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 22px;
      font-weight: 500;
      margin: 0;
      color: var(--color-text-primary);
    }
    .pc-subtitle {
      margin: 0;
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .pc-card {
      padding: 16px;
    }
    .pc-grid {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .pc-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 8px 0;
      flex-wrap: wrap;
    }
    .pc-row-multi {
      justify-content: flex-start;
      gap: 8px;
    }
    .pc-row label {
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-size: 13px;
      color: var(--color-text-primary);
      font-weight: 500;
    }
    .pc-hint {
      color: var(--color-text-secondary);
      font-weight: 400;
      font-size: 12px;
    }
    .pc-inline-field {
      min-width: 240px;
    }
    .pc-progress {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 12px;
    }
    .pc-progress-label {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--color-text-secondary);
    }
    .pc-milestones {
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .pc-milestones li {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 0;
      font-size: 13px;
    }
    .pc-ms-label {
      flex: 1;
    }
    .pc-done { color: var(--color-success, #1e8e3e); }
    .pc-pending { color: var(--color-text-secondary, #5f6368); }
    .pk-loading {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 0;
      color: var(--color-text-secondary);
      font-size: 13px;
    }
    .pk-error {
      color: var(--color-error, #d93025);
      margin: 0;
      font-size: 13px;
    }
    .pk-empty {
      color: var(--color-text-secondary);
      margin: 0;
      font-size: 13px;
    }
    .pk-list {
      padding: 0;
    }
    .pk-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--color-text-secondary);
      font-size: 12px;
    }
    .pk-unsupported {
      color: var(--color-text-secondary);
      font-size: 12px;
      margin-left: 8px;
    }
    .btn-spinner {
      margin-right: 8px;
    }
  `],
})
export class PreferencesComponent implements OnInit {
  protected a11y = inject(A11yPrefsService);
  protected locale = inject(LocaleService);
  protected noob = inject(NoobModeService);
  protected tutorial = inject(TutorialModeService);
  protected explain = inject(ExplainModeService);
  protected onboarding = inject(OnboardingStateService);
  private recentPages = inject(RecentPagesService);
  private tabPrefs = inject(TabPersistenceService);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);
  private passkeyService = inject(PasskeyService);

  protected readonly catalogue = ONBOARDING_CATALOGUE;

  // Passkey card state.
  protected readonly passkeys = signal<PasskeyCredentialSummary[]>([]);
  protected readonly passkeysLoading = signal(false);
  protected readonly passkeyBusy = signal(false);
  protected readonly passkeyError = signal<string>('');
  protected readonly passkeySupported = this.passkeyService.isBrowserSupported();

  ngOnInit(): void {
    this.onboarding.registerCatalogue(ONBOARDING_CATALOGUE);
    this.onboarding.markDone('first-preference-visit');
    this.loadPasskeys();
  }

  // ── Passkey card handlers ────────────────────────────────────────

  private loadPasskeys(): void {
    this.passkeysLoading.set(true);
    this.passkeyError.set('');
    this.passkeyService
      .listCredentials()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (rows) => {
          this.passkeys.set(rows ?? []);
          this.passkeysLoading.set(false);
        },
        error: (err) => {
          this.passkeysLoading.set(false);
          this.passkeyError.set(
            err?.error?.detail ||
              'Could not load your passkeys. The backend may be restarting.',
          );
        },
      });
  }

  async addPasskey(): Promise<void> {
    if (this.passkeyBusy()) return;
    if (!this.passkeySupported) {
      this.snack.open('Your browser does not support passkeys.', 'OK', { duration: 3000 });
      return;
    }
    const label = (window.prompt(
      'Give this passkey a name (for example "MacBook Touch ID" or "YubiKey"):',
      this.suggestPasskeyLabel(),
    ) || '').trim();
    if (label === '') {
      // User pressed Cancel — abort silently.
      return;
    }

    this.passkeyBusy.set(true);
    const result = await this.passkeyService.register(label);
    this.passkeyBusy.set(false);

    if (result.ok) {
      this.snack.open('Passkey added. You can now sign in with it.', 'OK', { duration: 3500 });
      this.loadPasskeys();
      return;
    }
    if (result.reason === 'cancelled') {
      // User pressed Cancel in the WebAuthn prompt. No need to nag.
      return;
    }
    if (result.reason === 'unsupported') {
      this.snack.open('Your browser does not support passkeys.', 'OK', { duration: 3000 });
      return;
    }
    if (result.reason === 'not-configured') {
      this.snack.open(
        'Passkey enrolment is not configured on this server. See docs/PASSKEY-SETUP.md.',
        'OK',
        { duration: 5000 },
      );
      return;
    }
    this.snack.open(
      result.detail || 'Passkey enrolment failed. Try again or check the console.',
      'OK',
      { duration: 4500 },
    );
  }

  renamePasskey(cred: PasskeyCredentialSummary): void {
    const next = (window.prompt(
      'New name for this passkey:',
      cred.label || '',
    ) || '').trim();
    if (next === '' || next === cred.label) return;
    this.passkeyService
      .relabelCredential(cred.id, next)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.snack.open('Passkey renamed.', 'OK', { duration: 2000 });
          this.loadPasskeys();
        },
        error: (err) =>
          this.snack.open(
            err?.error?.detail || 'Could not rename this passkey.',
            'OK',
            { duration: 3500 },
          ),
      });
  }

  deletePasskey(cred: PasskeyCredentialSummary): void {
    if (
      !window.confirm(
        `Delete the passkey "${cred.label || 'Unnamed passkey'}"? You will not be able to use it to sign in afterward.`,
      )
    ) {
      return;
    }
    this.passkeyService
      .deleteCredential(cred.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.snack.open('Passkey deleted.', 'OK', { duration: 2500 });
          this.loadPasskeys();
        },
        error: (err) =>
          this.snack.open(
            err?.error?.detail || 'Could not delete this passkey.',
            'OK',
            { duration: 4500 },
          ),
      });
  }

  formatRelative(iso: string): string {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return iso;
    const diffMs = Date.now() - t;
    const sec = Math.round(diffMs / 1000);
    if (sec < 60) return 'just now';
    const min = Math.round(sec / 60);
    if (min < 60) return `${min} min ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr} h ago`;
    const day = Math.round(hr / 24);
    if (day < 30) return `${day} day${day === 1 ? '' : 's'} ago`;
    const mo = Math.round(day / 30);
    if (mo < 12) return `${mo} mo ago`;
    const yr = Math.round(mo / 12);
    return `${yr} yr ago`;
  }

  private suggestPasskeyLabel(): string {
    if (typeof navigator === 'undefined') return '';
    const ua = navigator.userAgent || '';
    if (/Mac/.test(ua)) return 'Mac';
    if (/Windows/.test(ua)) return 'Windows PC';
    if (/Android/.test(ua)) return 'Android phone';
    if (/iPhone|iPad|iOS/.test(ua)) return 'iPhone / iPad';
    return 'This device';
  }

  onLocaleChange(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value.trim();
    if (!v) return;
    this.locale.setLocale(v);
    this.snack.open(`Locale → ${v}`, 'OK', { duration: 2500 });
  }

  onTimezoneChange(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value.trim();
    if (!v) return;
    try {
      // Validate by constructing a formatter; invalid names throw.
      new Intl.DateTimeFormat('en', { timeZone: v });
    } catch {
      this.snack.open(`Unknown timezone: ${v}`, 'OK', { duration: 3000 });
      return;
    }
    this.locale.setTimezone(v);
    this.snack.open(`Timezone → ${v}`, 'OK', { duration: 2500 });
  }

  onCurrencyChange(ev: Event): void {
    const v = (ev.target as HTMLInputElement).value.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(v)) {
      this.snack.open('Currency must be a 3-letter ISO 4217 code.', 'OK', {
        duration: 3000,
      });
      return;
    }
    this.locale.setCurrency(v);
    this.snack.open(`Currency → ${v}`, 'OK', { duration: 2500 });
  }

  clearRecentPages(): void {
    this.recentPages.clear();
    this.snack.open('Recent-pages history cleared.', 'OK', { duration: 2500 });
  }

  clearTabPrefs(): void {
    this.tabPrefs.clearAll();
    this.snack.open(
      'Remembered tab positions cleared. They will reset on your next visit.',
      'OK',
      { duration: 3500 },
    );
  }

  resetA11yPrefs(): void {
    this.a11y.resetAll();
    this.snack.open('Accessibility preferences reset to defaults.', 'OK', {
      duration: 2500,
    });
  }

  confirmAndResetOnboarding(): void {
    if (
      !window.confirm(
        'Reset every onboarding hint, tour, and discovery callout? You will see them again next time.',
      )
    ) {
      return;
    }
    this.onboarding.resetAll();
    this.snack.open(
      'Onboarding reset — guided tours will show again.',
      'OK',
      { duration: 3500 },
    );
  }

  openFeatureRequestDialog(): void {
    this.dialog
      .open(FeatureRequestDialogComponent, {
        width: '520px',
        restoreFocus: true,
      })
      .afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        /* snackbar shown by the dialog itself */
      });
  }

  prettifyMilestone(id: string): string {
    return id
      .replace(/[-_.]/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }
}
