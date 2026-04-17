import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';

/**
 * Phase A1 — combined accessibility preferences service. Backs four
 * gaps that each toggle a global appearance attribute:
 *
 *   - Gap 98  High-contrast theme
 *   - Gap 99  Font-size preference (90 / 100 / 115 / 130 %)
 *   - Gap 100 Dyslexia-friendly font (OpenDyslexic-like opt-in)
 *   - Gap 101 Color-blind palette toggle (none / protanopia /
 *             deuteranopia / tritanopia safe palettes)
 *
 * Each preference is a signal stored in localStorage. Whenever a
 * preference changes, the service writes a `data-*` attribute (or
 * `class`) onto `<html>` so global CSS can react with a single
 * selector. Components don't have to know about the service — they
 * just respect CSS variables that change shape under different
 * preference combinations.
 *
 * Conventions:
 *   data-contrast = 'high' | (none)
 *   data-font-size = '90' | '100' | '115' | '130'
 *   data-font-stack = 'dyslexia' | (none)
 *   data-cvd-palette = 'none' | 'protanopia' | 'deuteranopia' | 'tritanopia'
 *
 * The CSS that maps these attributes to colour and size variables
 * lives in `styles/_a11y.scss`.
 */

const KEY_CONTRAST = 'xfil_a11y_contrast';
const KEY_FONT_SIZE = 'xfil_a11y_font_size';
const KEY_FONT_STACK = 'xfil_a11y_font_stack';
const KEY_CVD = 'xfil_a11y_cvd_palette';

export type ContrastMode = 'normal' | 'high';
export type FontSizePref = 90 | 100 | 115 | 130;
export type FontStackPref = 'system' | 'dyslexia';
export type CvdPalette = 'none' | 'protanopia' | 'deuteranopia' | 'tritanopia';

@Injectable({ providedIn: 'root' })
export class A11yPrefsService {
  private readonly doc = inject(DOCUMENT);

  readonly contrast = signal<ContrastMode>(this.read(KEY_CONTRAST, 'normal') as ContrastMode);
  readonly fontSize = signal<FontSizePref>(
    Number(this.read(KEY_FONT_SIZE, '100')) as FontSizePref,
  );
  readonly fontStack = signal<FontStackPref>(this.read(KEY_FONT_STACK, 'system') as FontStackPref);
  readonly cvdPalette = signal<CvdPalette>(this.read(KEY_CVD, 'none') as CvdPalette);

  constructor() {
    // Mirror every preference signal onto <html> data-attributes so
    // global CSS picks up changes synchronously.
    effect(() => {
      const html = this.doc.documentElement;
      if (this.contrast() === 'high') html.setAttribute('data-contrast', 'high');
      else html.removeAttribute('data-contrast');
    });
    effect(() => {
      this.doc.documentElement.setAttribute(
        'data-font-size',
        String(this.fontSize()),
      );
    });
    effect(() => {
      const html = this.doc.documentElement;
      if (this.fontStack() === 'dyslexia') html.setAttribute('data-font-stack', 'dyslexia');
      else html.removeAttribute('data-font-stack');
    });
    effect(() => {
      const html = this.doc.documentElement;
      const v = this.cvdPalette();
      if (v === 'none') html.removeAttribute('data-cvd-palette');
      else html.setAttribute('data-cvd-palette', v);
    });
  }

  // ── setters with persistence ──────────────────────────────────────

  setContrast(v: ContrastMode): void {
    this.contrast.set(v);
    this.persist(KEY_CONTRAST, v);
  }

  toggleContrast(): void {
    this.setContrast(this.contrast() === 'high' ? 'normal' : 'high');
  }

  setFontSize(v: FontSizePref): void {
    this.fontSize.set(v);
    this.persist(KEY_FONT_SIZE, String(v));
  }

  setFontStack(v: FontStackPref): void {
    this.fontStack.set(v);
    this.persist(KEY_FONT_STACK, v);
  }

  toggleDyslexiaFont(): void {
    this.setFontStack(this.fontStack() === 'dyslexia' ? 'system' : 'dyslexia');
  }

  setCvdPalette(v: CvdPalette): void {
    this.cvdPalette.set(v);
    this.persist(KEY_CVD, v);
  }

  /** Reset every accessibility preference to its default. Wired to
   *  the User Preference Center "reset" button. */
  resetAll(): void {
    this.setContrast('normal');
    this.setFontSize(100);
    this.setFontStack('system');
    this.setCvdPalette('none');
  }

  // ── helpers ────────────────────────────────────────────────────────

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
      // Private mode — in-memory only.
    }
  }
}
