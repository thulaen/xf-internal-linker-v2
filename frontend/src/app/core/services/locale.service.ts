import { Injectable, inject, signal } from '@angular/core';
import { LOCALE_ID } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';

/**
 * Phase A1 — combined locale service powering:
 *   - Gap 105 i18n scaffolding (locale id + future translation key
 *             catalog hook)
 *   - Gap 106 Number / date / currency localisation via Intl
 *   - Gap 107 Timezone awareness (resolved from Intl, overridable)
 *
 * Why a single service instead of three:
 *   Locale, currency, and timezone are tightly coupled. A user who
 *   changes their preferred language to fr-FR almost certainly wants
 *   French number formats, EUR currency by default, and Europe/Paris
 *   for date display. Bundling the three lets us apply or override
 *   them as a unit.
 *
 * Defaults are pulled from the browser at bootstrap time so the
 * dashboard speaks the user's language out of the box. Overrides
 * persist in localStorage.
 */

const KEY_LOCALE = 'xfil_locale';
const KEY_TIMEZONE = 'xfil_timezone';
const KEY_CURRENCY = 'xfil_currency';

@Injectable({ providedIn: 'root' })
export class LocaleService {
  private readonly initialLocale = inject(LOCALE_ID, { optional: true }) ?? 'en-US';

  readonly locale = signal<string>(this.read(KEY_LOCALE, this.detectLocale()));
  readonly timezone = signal<string>(this.read(KEY_TIMEZONE, this.detectTimezone()));
  readonly currency = signal<string>(this.read(KEY_CURRENCY, this.detectCurrency()));

  readonly locale$ = toObservable(this.locale);

  setLocale(v: string): void {
    this.locale.set(v);
    this.persist(KEY_LOCALE, v);
  }

  setTimezone(v: string): void {
    this.timezone.set(v);
    this.persist(KEY_TIMEZONE, v);
  }

  setCurrency(v: string): void {
    this.currency.set(v);
    this.persist(KEY_CURRENCY, v);
  }

  // ── pure formatting helpers (used by pipes too) ───────────────────

  /** Format a number using the active locale.
   *  Defaults to no fraction-digit constraints — pass options for currency etc. */
  formatNumber(n: number, opts?: Intl.NumberFormatOptions): string {
    if (!Number.isFinite(n)) return '';
    try {
      return new Intl.NumberFormat(this.locale(), opts).format(n);
    } catch {
      return n.toLocaleString();
    }
  }

  /** Format a value as currency using the user's currency preference. */
  formatCurrency(amount: number, currencyOverride?: string): string {
    return this.formatNumber(amount, {
      style: 'currency',
      currency: currencyOverride ?? this.currency(),
    });
  }

  /** Format a date in the user's locale + timezone.
   *  Accepts ISO strings, numbers (ms epoch), or Date objects. */
  formatDate(
    value: string | number | Date,
    opts: Intl.DateTimeFormatOptions = { dateStyle: 'medium' },
  ): string {
    const d = this.toDate(value);
    if (!d) return '';
    try {
      return new Intl.DateTimeFormat(this.locale(), {
        timeZone: this.timezone(),
        ...opts,
      }).format(d);
    } catch {
      return d.toString();
    }
  }

  /** Format a date+time. Default: medium date + short time. */
  formatDateTime(value: string | number | Date): string {
    return this.formatDate(value, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  }

  // ── detection ──────────────────────────────────────────────────────

  private detectLocale(): string {
    if (typeof navigator !== 'undefined' && navigator.language) {
      return navigator.language;
    }
    return this.initialLocale;
  }

  private detectTimezone(): string {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch {
      return 'UTC';
    }
  }

  private detectCurrency(): string {
    // Intl gives us locale's region; we map a couple of common ones to
    // the natural currency. Anything we don't recognise falls back to
    // USD so prices still render rather than throwing.
    const loc = this.detectLocale();
    const region = loc.split('-')[1]?.toUpperCase();
    switch (region) {
      case 'US': return 'USD';
      case 'GB': return 'GBP';
      case 'EU': case 'FR': case 'DE': case 'IT': case 'ES': case 'NL':
      case 'IE': case 'PT': case 'AT': case 'BE': case 'FI': case 'GR':
        return 'EUR';
      case 'JP': return 'JPY';
      case 'CN': return 'CNY';
      case 'IN': return 'INR';
      case 'CA': return 'CAD';
      case 'AU': return 'AUD';
      case 'BR': return 'BRL';
      case 'MX': return 'MXN';
      case 'KR': return 'KRW';
      default: return 'USD';
    }
  }

  // ── persistence ────────────────────────────────────────────────────

  private read(key: string, fallback: string): string {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  }

  private persist(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      // No-op.
    }
  }

  private toDate(value: string | number | Date): Date | null {
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
    if (typeof value === 'number') {
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    if (typeof value === 'string') {
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    return null;
  }
}
