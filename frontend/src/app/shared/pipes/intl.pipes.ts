import { Pipe, PipeTransform, inject } from '@angular/core';

import { LocaleService } from '../../core/services/locale.service';

/**
 * Phase A1 / Gap 106 — Intl-backed number/currency/date pipes.
 *
 * These wrap LocaleService so templates pick up the user's preferred
 * locale + timezone + currency without each component having to inject
 * the service. All pipes are pure — invalidate when their inputs
 * change. (LocaleService changes don't invalidate currently — flip the
 * surrounding `*ngIf` or hard-reload to re-render after a locale flip.
 * For interactive locale switching a follow-up session can convert
 * these to impure pipes or signal-driven equivalents.)
 *
 * Usage:
 *   {{ 1234567 | intlNumber }}              → 1,234,567 (en-US)
 *   {{ 19.95 | intlCurrency:'EUR' }}        → €19.95
 *   {{ ts | intlDate:'short' }}             → 4/17/26
 *   {{ ts | intlDateTime }}                 → Apr 17, 2026, 9:42 AM
 */

@Pipe({ name: 'intlNumber', standalone: true })
export class IntlNumberPipe implements PipeTransform {
  private readonly locale = inject(LocaleService);
  transform(value: number | null | undefined, opts?: Intl.NumberFormatOptions): string {
    if (value === null || value === undefined) return '';
    return this.locale.formatNumber(value, opts);
  }
}

@Pipe({ name: 'intlCurrency', standalone: true })
export class IntlCurrencyPipe implements PipeTransform {
  private readonly locale = inject(LocaleService);
  transform(value: number | null | undefined, currencyOverride?: string): string {
    if (value === null || value === undefined) return '';
    return this.locale.formatCurrency(value, currencyOverride);
  }
}

/** Format a Date / ISO / epoch value.
 *  `style` accepts the Intl shortcut keys (short/medium/long/full) OR
 *  a full Intl.DateTimeFormatOptions object for fine-grained control. */
@Pipe({ name: 'intlDate', standalone: true })
export class IntlDatePipe implements PipeTransform {
  private readonly locale = inject(LocaleService);
  transform(
    value: string | number | Date | null | undefined,
    style: 'short' | 'medium' | 'long' | 'full' | Intl.DateTimeFormatOptions = 'medium',
  ): string {
    if (value === null || value === undefined) return '';
    const opts: Intl.DateTimeFormatOptions =
      typeof style === 'string' ? { dateStyle: style } : style;
    return this.locale.formatDate(value, opts);
  }
}

@Pipe({ name: 'intlDateTime', standalone: true })
export class IntlDateTimePipe implements PipeTransform {
  private readonly locale = inject(LocaleService);
  transform(value: string | number | Date | null | undefined): string {
    if (value === null || value === undefined) return '';
    return this.locale.formatDateTime(value);
  }
}
