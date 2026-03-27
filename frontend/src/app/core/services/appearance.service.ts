import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, catchError, map, of, tap } from 'rxjs';

export interface AppearanceConfig {
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
  /** Absolute URL to the uploaded site logo served from /media/. Empty string = no logo. */
  logoUrl: string;
  /** Absolute URL to the uploaded favicon served from /media/. Empty string = no favicon. */
  faviconUrl: string;
  presets: Array<{ name: string; config: Partial<AppearanceConfig> }>;
}

export const DEFAULT_CONFIG: AppearanceConfig = {
  primaryColor: '#1a73e8',
  accentColor: '#f4b400',
  fontSize: 'medium',
  layoutWidth: 'standard',
  sidebarWidth: 'standard',
  density: 'comfortable',
  headerBg: '#ffffff',
  siteName: 'XF Internal Linker',
  showScrollToTop: true,
  footerText: 'XF Internal Linker V2',
  showFooter: true,
  footerBg: '#f8f9fa',
  logoUrl: '',
  faviconUrl: '',
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

  /**
   * Upload a site logo (PNG / SVG / WEBP / JPEG, max 2 MB).
   * On success the config's logoUrl is updated automatically.
   */
  uploadLogo(file: File): Observable<string> {
    const form = new FormData();
    form.append('file', file);
    return this.http
      .post<{ logo_url: string }>('/api/settings/logo/', form)
      .pipe(
        tap((res) => this.update({ logoUrl: res.logo_url })),
        map((res) => res.logo_url),
      );
  }

  /** Remove the site logo and clear logoUrl. */
  removeLogo(): void {
    this.http.delete('/api/settings/logo/').pipe(catchError(() => of(null))).subscribe();
    this.update({ logoUrl: '' });
  }

  /**
   * Upload a site favicon (PNG / SVG / ICO, max 2 MB).
   * On success the config's faviconUrl is updated automatically.
   */
  uploadFavicon(file: File): Observable<string> {
    const form = new FormData();
    form.append('file', file);
    return this.http
      .post<{ favicon_url: string }>('/api/settings/favicon/', form)
      .pipe(
        tap((res) => this.update({ faviconUrl: res.favicon_url })),
        map((res) => res.favicon_url),
      );
  }

  /** Remove the site favicon and clear faviconUrl. */
  removeFavicon(): void {
    this.http.delete('/api/settings/favicon/').pipe(catchError(() => of(null))).subscribe();
    this.update({ faviconUrl: '' });
  }

  private applyToDom(cfg: AppearanceConfig): void {
    const root = document.documentElement;

    // Color properties — validate hex format before applying to prevent
    // malformed values from producing unexpected CSS output.
    if (this.isHexColor(cfg.primaryColor)) {
      root.style.setProperty('--color-primary', cfg.primaryColor);
      root.style.setProperty('--color-primary-medium', cfg.primaryColor);
    }
    if (this.isHexColor(cfg.accentColor)) {
      root.style.setProperty('--color-accent', cfg.accentColor);
    }
    if (this.isHexColor(cfg.headerBg)) {
      root.style.setProperty('--toolbar-bg', cfg.headerBg);
    }
    if (this.isHexColor(cfg.footerBg)) {
      root.style.setProperty('--footer-bg', cfg.footerBg);
    }

    // Enum values resolved through allow-lists — never passed raw
    root.style.setProperty('--font-size-base', FONT_SIZE_MAP[cfg.fontSize] ?? '14px');
    root.style.setProperty('--layout-max-width', LAYOUT_WIDTH_MAP[cfg.layoutWidth] ?? '1280px');
    root.style.setProperty('--sidenav-width', SIDEBAR_WIDTH_MAP[cfg.sidebarWidth] ?? '220px');

    // Page title — plain text assignment, no HTML involved
    if (cfg.siteName) {
      document.title = cfg.siteName;
    }

    // Favicon — find or create the <link rel="icon"> element in <head>
    if (cfg.faviconUrl) {
      let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
      if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        document.head.appendChild(link);
      }
      link.href = cfg.faviconUrl;
    }
  }

  /** Returns true for 3- and 6-digit hex color strings (e.g. #1a73e8). */
  private isHexColor(value: string): boolean {
    return /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(value ?? '');
  }
}
