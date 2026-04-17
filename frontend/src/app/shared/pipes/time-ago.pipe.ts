import { ChangeDetectorRef, OnDestroy, Pipe, PipeTransform, inject } from '@angular/core';

import { LocaleService } from '../../core/services/locale.service';

/**
 * Phase A1 / Gap 108 — Humanised relative dates.
 *
 * Wraps `Intl.RelativeTimeFormat` to render "3 minutes ago",
 * "in 2 days", etc., in the user's preferred locale. Self-refreshes
 * every 30 seconds so the relative label stays accurate without
 * requiring the parent component to re-tick.
 *
 * Why impure: pure pipes don't recompute when the wall-clock advances.
 * Cost is one CD pass per pipe instance per 30s — cheap.
 *
 * Usage:
 *   {{ alert.first_seen_at | timeAgo }}    → "3 minutes ago"
 *   {{ alert.first_seen_at | timeAgo:'short' }}  → "3m ago"
 */
@Pipe({ name: 'timeAgo', standalone: true, pure: false })
export class TimeAgoPipe implements PipeTransform, OnDestroy {
  private readonly locale = inject(LocaleService);
  private readonly cdr = inject(ChangeDetectorRef);

  private timer: ReturnType<typeof setInterval> | null = null;
  private lastValue: string | number | Date | null | undefined = undefined;
  private lastStyle: 'long' | 'short' = 'long';
  private cached = '';

  transform(
    value: string | number | Date | null | undefined,
    style: 'long' | 'short' = 'long',
  ): string {
    if (value === null || value === undefined) return '';
    if (value !== this.lastValue || style !== this.lastStyle) {
      this.lastValue = value;
      this.lastStyle = style;
      this.cached = this.compute(value, style);
      this.ensureTimer();
    } else {
      this.cached = this.compute(value, style);
    }
    return this.cached;
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  // ── internals ──────────────────────────────────────────────────────

  private ensureTimer(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      // Mark dirty; Angular will call transform() again on the next CD.
      this.cdr.markForCheck();
    }, 30_000);
  }

  private compute(value: string | number | Date, style: 'long' | 'short'): string {
    const d = this.toDate(value);
    if (!d) return '';
    const diffMs = d.getTime() - Date.now();
    return this.format(diffMs, style);
  }

  private format(diffMs: number, style: 'long' | 'short'): string {
    const absMs = Math.abs(diffMs);
    const units: { ms: number; unit: Intl.RelativeTimeFormatUnit }[] = [
      { ms: 365 * 86_400_000, unit: 'year' },
      { ms: 30 * 86_400_000, unit: 'month' },
      { ms: 7 * 86_400_000, unit: 'week' },
      { ms: 86_400_000, unit: 'day' },
      { ms: 3_600_000, unit: 'hour' },
      { ms: 60_000, unit: 'minute' },
      { ms: 1_000, unit: 'second' },
    ];
    let chosen: { ms: number; unit: Intl.RelativeTimeFormatUnit } = units[units.length - 1];
    for (const u of units) {
      if (absMs >= u.ms) {
        chosen = u;
        break;
      }
    }
    const value = Math.round(diffMs / chosen.ms);
    try {
      const fmt = new Intl.RelativeTimeFormat(this.locale.locale(), {
        numeric: 'auto',
        style: style === 'short' ? 'short' : 'long',
      });
      return fmt.format(value, chosen.unit);
    } catch {
      // Pre-Intl-RTF fallback (very old browsers).
      const ago = diffMs <= 0 ? 'ago' : 'from now';
      return `${Math.abs(value)} ${chosen.unit}${Math.abs(value) === 1 ? '' : 's'} ${ago}`;
    }
  }

  private toDate(value: string | number | Date): Date | null {
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
    if (typeof value === 'number') {
      const d = new Date(value);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
}
