import { Component, EventEmitter, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
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
    MatSelectModule,
    MatSlideToggleModule,
    MatTooltipModule,
  ],
  templateUrl: './theme-customizer.component.html',
  styleUrls: ['./theme-customizer.component.scss'],
})
export class ThemeCustomizerComponent {
  @Output() close = new EventEmitter<void>();

  appearance = inject(AppearanceService);

  newPresetName = '';
  showSavePreset = false;

  get cfg(): AppearanceConfig {
    return this.appearance.config;
  }

  setPrimary(color: string): void {
    this.appearance.update({ primaryColor: color });
  }

  setAccent(color: string): void {
    this.appearance.update({ accentColor: color });
  }

  setHeaderBg(color: string): void {
    this.appearance.update({ headerBg: color });
  }

  setFooterBg(color: string): void {
    this.appearance.update({ footerBg: color });
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
    this.appearance.update({ siteName: name });
  }

  setFooterText(text: string): void {
    this.appearance.update({ footerText: text });
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
