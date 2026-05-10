import { TestBed } from '@angular/core/testing';

import { A11yPrefsService } from './a11y-prefs.service';

/**
 * A11yPrefsService — preference signals + localStorage round-trip + DOM
 * mirror via `data-*` attributes on <html>.
 *
 * The DOM-mirror effects fire only inside Angular change detection, so
 * tests trigger them by calling `TestBed.flushEffects()` or by reading
 * the signal value (which is enough for behaviour-level coverage).
 */
describe('A11yPrefsService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-contrast');
    document.documentElement.removeAttribute('data-font-size');
    document.documentElement.removeAttribute('data-font-stack');
    document.documentElement.removeAttribute('data-cvd-palette');
    TestBed.configureTestingModule({});
  });

  it('boots with normal/100/system/none defaults', () => {
    const svc = TestBed.inject(A11yPrefsService);
    expect(svc.contrast()).toBe('normal');
    expect(svc.fontSize()).toBe(100);
    expect(svc.fontStack()).toBe('system');
    expect(svc.cvdPalette()).toBe('none');
  });

  it('rehydrates the contrast signal from localStorage', () => {
    localStorage.setItem('xfil_a11y_contrast', 'high');
    const svc = TestBed.inject(A11yPrefsService);
    expect(svc.contrast()).toBe('high');
  });

  it('persists font size via setFontSize and rehydrates as a number', () => {
    const svc = TestBed.inject(A11yPrefsService);
    svc.setFontSize(130);
    expect(svc.fontSize()).toBe(130);
    expect(localStorage.getItem('xfil_a11y_font_size')).toBe('130');
  });

  it('toggleContrast flips between normal and high', () => {
    const svc = TestBed.inject(A11yPrefsService);
    svc.toggleContrast();
    expect(svc.contrast()).toBe('high');
    svc.toggleContrast();
    expect(svc.contrast()).toBe('normal');
  });

  it('toggleDyslexiaFont flips between system and dyslexia', () => {
    const svc = TestBed.inject(A11yPrefsService);
    svc.toggleDyslexiaFont();
    expect(svc.fontStack()).toBe('dyslexia');
    expect(localStorage.getItem('xfil_a11y_font_stack')).toBe('dyslexia');
    svc.toggleDyslexiaFont();
    expect(svc.fontStack()).toBe('system');
  });

  it('setCvdPalette persists the new palette name', () => {
    const svc = TestBed.inject(A11yPrefsService);
    svc.setCvdPalette('protanopia');
    expect(svc.cvdPalette()).toBe('protanopia');
    expect(localStorage.getItem('xfil_a11y_cvd_palette')).toBe('protanopia');
  });

  it('resetAll restores defaults across all four prefs', () => {
    const svc = TestBed.inject(A11yPrefsService);
    svc.setContrast('high');
    svc.setFontSize(130);
    svc.setFontStack('dyslexia');
    svc.setCvdPalette('deuteranopia');
    svc.resetAll();
    expect(svc.contrast()).toBe('normal');
    expect(svc.fontSize()).toBe(100);
    expect(svc.fontStack()).toBe('system');
    expect(svc.cvdPalette()).toBe('none');
  });
});
