import { Component, EventEmitter, Output, inject } from '@angular/core';
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
import { AppearanceService, AppearanceConfig } from '../core/services/appearance.service';

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
})
export class ThemeCustomizerComponent {
  // eslint-disable-next-line @angular-eslint/no-output-native
  @Output() close = new EventEmitter<void>();

  appearance = inject(AppearanceService);
  private snack = inject(MatSnackBar);

  newPresetName = '';
  showSavePreset = false;
  uploadingLogo = false;
  uploadingFavicon = false;

  get cfg(): AppearanceConfig {
    return this.appearance.config;
  }

  onLogoChange(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.uploadingLogo = true;
    this.appearance.uploadLogo(file).subscribe({
      next: () => {
        this.uploadingLogo = false;
        this.snack.open('Logo uploaded', 'Dismiss', { duration: 3000 });
      },
      error: (err) => {
        this.uploadingLogo = false;
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
    this.uploadingFavicon = true;
    this.appearance.uploadFavicon(file).subscribe({
      next: () => {
        this.uploadingFavicon = false;
        this.snack.open('Favicon uploaded', 'Dismiss', { duration: 3000 });
      },
      error: (err) => {
        this.uploadingFavicon = false;
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
      this.showSavePreset = false;
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
