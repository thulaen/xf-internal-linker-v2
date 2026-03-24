import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, catchError, of, tap } from 'rxjs';

export interface AppearanceConfig {
  theme: 'light' | 'dark';
  primaryColor: string;
  accentColor: string;
  fontSize: 'small' | 'medium' | 'large';
  layoutWidth: 'narrow' | 'standard' | 'wide';
  sidebarWidth: 'compact' | 'standard' | 'comfortable';
  density: 'compact' | 'comfortable';
  headerBg: string;
  siteName: string;
  showScrollToTop: boolean;
  footerText: string;
  showFooter: boolean;
  footerBg: string;
  presets: Array<{ name: string; config: Partial<AppearanceConfig> }>;
}

export const DEFAULT_CONFIG: AppearanceConfig = {
  theme: 'light',
  primaryColor: '#1a73e8',
  accentColor: '#f4b400',
  fontSize: 'medium',
  layoutWidth: 'standard',
  sidebarWidth: 'standard',
  density: 'comfortable',
  headerBg: '#0b57d0',
  siteName: 'XF Internal Linker',
  showScrollToTop: true,
  footerText: 'XF Internal Linker V2',
  showFooter: true,
  footerBg: '#f8f9fa',
  presets: [],
};

const FONT_SIZE_MAP: Record<string, string> = {
  small: '13px',
  medium: '14px',
  large: '16px',
};

const LAYOUT_WIDTH_MAP: Record<string, string> = {
  narrow: '960px',
  standard: '1280px',
  wide: '100%',
};

const SIDEBAR_WIDTH_MAP: Record<string, string> = {
  compact: '200px',
  standard: '220px',
  comfortable: '260px',
};

@Injectable({ providedIn: 'root' })
export class AppearanceService {
  private http = inject(HttpClient);
  private apiUrl = '/api/settings/appearance/';

  private _config$ = new BehaviorSubject<AppearanceConfig>(DEFAULT_CONFIG);
  readonly config$ = this._config$.asObservable();

  get config(): AppearanceConfig {
    return this._config$.getValue();
  }

  /** Load settings from API and apply to DOM. Call once on app init. */
  load(): void {
    this.http
      .get<AppearanceConfig>(this.apiUrl)
      .pipe(catchError(() => of(DEFAULT_CONFIG)))
      .subscribe((cfg) => {
        const merged = { ...DEFAULT_CONFIG, ...cfg };
        this._config$.next(merged);
        this.applyToDom(merged);
      });
  }

  /** Update one or more keys, save to API, apply immediately. */
  update(patch: Partial<AppearanceConfig>): void {
    const next = { ...this._config$.getValue(), ...patch };
    this._config$.next(next);
    this.applyToDom(next);
    this.http
      .put<AppearanceConfig>(this.apiUrl, patch)
      .pipe(catchError(() => of(next)))
      .subscribe();
  }

  /** Reset to factory defaults, persist. */
  reset(): void {
    const defaults = { ...DEFAULT_CONFIG, presets: this.config.presets };
    this.update(defaults);
  }

  /** Save current config as a named preset. */
  savePreset(name: string): void {
    const { presets, ...rest } = this.config;
    const updated = presets.filter((p) => p.name !== name);
    updated.push({ name, config: rest });
    this.update({ presets: updated });
  }

  /** Load a saved preset (merges, keeps existing presets list). */
  loadPreset(name: string): void {
    const preset = this.config.presets.find((p) => p.name === name);
    if (preset) this.update(preset.config);
  }

  /** Delete a saved preset by name. */
  deletePreset(name: string): void {
    const presets = this.config.presets.filter((p) => p.name !== name);
    this.update({ presets });
  }

  private applyToDom(cfg: AppearanceConfig): void {
    const root = document.documentElement;

    // Theme (light/dark)
    root.setAttribute('data-theme', cfg.theme);

    // Primary color
    root.style.setProperty('--color-primary', cfg.primaryColor);
    root.style.setProperty('--color-primary-medium', cfg.primaryColor);

    // Accent color
    root.style.setProperty('--color-accent', cfg.accentColor);

    // Toolbar background (header)
    root.style.setProperty('--toolbar-bg', cfg.headerBg);

    // Footer background
    root.style.setProperty('--footer-bg', cfg.footerBg);

    // Font size
    root.style.setProperty('--font-size-base', FONT_SIZE_MAP[cfg.fontSize] ?? '14px');

    // Layout max-width
    root.style.setProperty('--layout-max-width', LAYOUT_WIDTH_MAP[cfg.layoutWidth] ?? '1280px');

    // Sidebar width
    root.style.setProperty('--sidenav-width', SIDEBAR_WIDTH_MAP[cfg.sidebarWidth] ?? '220px');

    // Page title
    document.title = cfg.siteName;
  }
}
