import { ChangeDetectionStrategy, Component, DestroyRef, EventEmitter, Output, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { AppearanceService } from '../core/services/appearance.service';

@Component({
  selector: 'app-theme-customizer',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './theme-customizer.component.html',
  styleUrls: ['./theme-customizer.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThemeCustomizerComponent {
  // eslint-disable-next-line @angular-eslint/no-output-native
  @Output() close = new EventEmitter<void>();

  appearance = inject(AppearanceService);
  private snack = inject(MatSnackBar);
  // Phase E2 / Gap 41 — cancel in-flight uploads on destroy.
  private destroyRef = inject(DestroyRef);

  // ngModel two-way binding requires an lvalue, so this stays plain.
  // Input events fire on the host and trigger CD per keystroke under
  // OnPush, so the bindings that read it stay in sync.
  newPresetName = '';

  // Render-affecting state lives in signals so OnPush picks up changes
  // without markForCheck plumbing.
  readonly showSavePreset = signal(false);
  readonly uploadingLogo = signal(false);
  readonly uploadingFavicon = signal(false);

  // The live theme preview is driven by AppearanceService.config$
  // (a BehaviorSubject-backed Observable that emits synchronously on
  // subscribe). toSignal with `requireSync: true` returns a non-
  // nullable Signal<AppearanceConfig> — when the service emits a new
  // config (after setPrimary, loadPreset, etc.) every cfg().X binding
  // re-evaluates automatically. Replaces the previous `get cfg()`
  // getter, which was a snapshot read that wouldn't refresh under
  // OnPush change detection.
  readonly cfg = toSignal(this.appearance.config$, { requireSync: true });

  onLogoChange(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.uploadingLogo.set(true);
    this.appearance.uploadLogo(file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.uploadingLogo.set(false);
        this.snack.open('Logo uploaded', 'Dismiss', { duration: 3000 });
      },
      error: (err) => {
        this.uploadingLogo.set(false);
        const msg = err?.error?.error ?? 'Logo upload failed.';
        this.snack.open(msg, 'Dismiss', { duration: 5000 });
      },
    });
    // Reset input so the same file can be re-selected after removal
    (event.target as HTMLInputElement).value = '';
  }

  removeLogo(): void {
    this.appearance.removeLogo();
    this.snack.open('Logo removed', 'Dismiss', { duration: 3000 });
  }

  onFaviconChange(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.uploadingFavicon.set(true);
    this.appearance.uploadFavicon(file)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
      next: () => {
        this.uploadingFavicon.set(false);
        this.snack.open('Favicon uploaded', 'Dismiss', { duration: 3000 });
      },
      error: (err) => {
        this.uploadingFavicon.set(false);
        const msg = err?.error?.error ?? 'Favicon upload failed.';
        this.snack.open(msg, 'Dismiss', { duration: 5000 });
      },
    });
    (event.target as HTMLInputElement).value = '';
  }

  removeFavicon(): void {
    this.appearance.removeFavicon();
    this.snack.open('Favicon removed', 'Dismiss', { duration: 3000 });
  }

  setPrimary(color: string): void {
    this.appearance.update({ primaryColor: color }, true);
  }

  setAccent(color: string): void {
    this.appearance.update({ accentColor: color }, true);
  }

  setHeaderBg(color: string): void {
    this.appearance.update({ headerBg: color }, true);
  }

  setFooterBg(color: string): void {
    this.appearance.update({ footerBg: color }, true);
  }

  setFontSize(size: 'small' | 'medium' | 'large'): void {
    this.appearance.update({ fontSize: size });
  }

  setLayoutWidth(w: 'narrow' | 'standard' | 'wide'): void {
    this.appearance.update({ layoutWidth: w });
  }

  setSidebarWidth(w: 'compact' | 'standard' | 'comfortable'): void {
    this.appearance.update({ sidebarWidth: w });
  }

  setDensity(d: 'compact' | 'comfortable'): void {
    this.appearance.update({ density: d });
  }

  setSiteName(name: string): void {
    this.appearance.update({ siteName: name }, true);
  }

  setFooterText(text: string): void {
    this.appearance.update({ footerText: text }, true);
  }

  toggleFooter(show: boolean): void {
    this.appearance.update({ showFooter: show });
  }

  toggleScrollToTop(show: boolean): void {
    this.appearance.update({ showScrollToTop: show });
  }

  savePreset(): void {
    if (this.newPresetName.trim()) {
      this.appearance.savePreset(this.newPresetName.trim());
      this.newPresetName = '';
      this.showSavePreset.set(false);
    }
  }

  loadPreset(name: string): void {
    this.appearance.loadPreset(name);
  }

  deletePreset(name: string): void {
    this.appearance.deletePreset(name);
  }

  reset(): void {
    this.appearance.reset();
  }
}
