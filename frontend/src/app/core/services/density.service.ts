import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';

/**
 * Phase GK2 / Gap 229 + 251 — Global row-density preference.
 *
 * Three levels: compact / comfortable / spacious. Persists in
 * localStorage and mirrors onto `<html data-density="...">` so any
 * component can respond via CSS without injecting this service.
 *
 * Complements the existing Gap 99 font-size toggle — density changes
 * vertical rhythm (padding between rows, line-height) while font-size
 * changes base text size. They compose without conflict.
 */

export type DensityLevel = 'compact' | 'comfortable' | 'spacious';

const KEY = 'xfil_density';
const ALLOWED: readonly DensityLevel[] = ['compact', 'comfortable', 'spacious'];

@Injectable({ providedIn: 'root' })
export class DensityService {
  private doc = inject(DOCUMENT);

  readonly density = signal<DensityLevel>(this.read());

  constructor() {
    effect(() => {
      this.doc.documentElement.setAttribute('data-density', this.density());
    });
  }

  set(next: DensityLevel): void {
    if (!ALLOWED.includes(next)) return;
    this.density.set(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* in-memory only */
    }
  }

  private read(): DensityLevel {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw && (ALLOWED as readonly string[]).includes(raw)) {
        return raw as DensityLevel;
      }
    } catch {
      /* ignore */
    }
    return 'comfortable';
  }
}
