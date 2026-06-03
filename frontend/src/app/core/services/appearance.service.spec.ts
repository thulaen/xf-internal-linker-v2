import { TestBed } from '@angular/core/testing';
import { BehaviorSubject } from 'rxjs';

import { AppearanceService, DEFAULT_CONFIG } from './appearance.service';
import { AuthService } from './auth.service';
import { HttpClient } from '@angular/common/http';
import { MatSnackBar } from '@angular/material/snack-bar';

// Focused unit tests for the brand-colour-override guard added 2026-05-30.
// The private `applyColorOverride` is the unit under test: it must keep the
// SCSS design token (`_theme-vars.scss`) as the source of truth and only set
// an inline CSS variable when the user customised the colour away from the
// default. These tests pin that exact behaviour so a future change cannot
// silently re-introduce the brand-colour override bug.
describe('AppearanceService.applyColorOverride', () => {
  let service: AppearanceService;

  beforeEach(() => {
    const authStub = { isLoggedIn$: new BehaviorSubject<boolean>(false) };
    const httpStub = { get: () => new BehaviorSubject(null), patch: () => new BehaviorSubject(null) };
    const snackStub = { open: () => undefined };

    TestBed.configureTestingModule({
      providers: [
        AppearanceService,
        { provide: AuthService, useValue: authStub },
        { provide: HttpClient, useValue: httpStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    });
    service = TestBed.inject(AppearanceService);
  });

  function applyOverride(el: HTMLElement, prop: string, value: string, def: string): void {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (service as any).applyColorOverride(el, prop, value, def);
  }

  it('removes the inline override when the value equals the default (token governs)', () => {
    const el = document.createElement('div');
    el.style.setProperty('--color-primary', '#000000');
    applyOverride(el, '--color-primary', DEFAULT_CONFIG.primaryColor, DEFAULT_CONFIG.primaryColor);
    expect(el.style.getPropertyValue('--color-primary')).toBe('');
  });

  it('removes the inline override when the default differs only by letter case', () => {
    const el = document.createElement('div');
    el.style.setProperty('--color-primary', '#111111');
    applyOverride(el, '--color-primary', '#4285F4', '#4285f4');
    expect(el.style.getPropertyValue('--color-primary')).toBe('');
  });

  it('sets the inline override when the user picked a different valid hex colour', () => {
    const el = document.createElement('div');
    applyOverride(el, '--color-primary', '#ff0000', DEFAULT_CONFIG.primaryColor);
    expect(el.style.getPropertyValue('--color-primary')).toBe('#ff0000');
  });

  it('removes the inline override when the customised value is not valid hex', () => {
    const el = document.createElement('div');
    el.style.setProperty('--color-primary', '#222222');
    applyOverride(el, '--color-primary', 'not-a-colour', DEFAULT_CONFIG.primaryColor);
    expect(el.style.getPropertyValue('--color-primary')).toBe('');
  });

  it('keeps GSC blue as the default brand colour', () => {
    expect(DEFAULT_CONFIG.primaryColor).toBe('#4285f4');
    expect(DEFAULT_CONFIG.accentColor).toBe('#4285f4');
  });
});
