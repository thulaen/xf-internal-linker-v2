import { TestBed } from '@angular/core/testing';
import { NoobModeService } from './noob-mode.service';

describe('NoobModeService', () => {
  beforeEach(() => localStorage.clear());

  function createService(): NoobModeService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(NoobModeService);
  }

  it('defaults to "noob" on a fresh install', () => {
    const service = createService();
    expect(service.mode()).toBe('noob');
  });

  it('rehydrates "pro" from localStorage', () => {
    localStorage.setItem('xfil_operator_mode', 'pro');
    const service = createService();
    expect(service.mode()).toBe('pro');
  });

  it('rehydrates anything other than "pro" as "noob"', () => {
    localStorage.setItem('xfil_operator_mode', 'expert');
    const service = createService();
    expect(service.mode()).toBe('noob');
  });

  it('setMode("pro") flips the signal and persists', () => {
    const service = createService();
    service.setMode('pro');
    expect(service.mode()).toBe('pro');
    expect(localStorage.getItem('xfil_operator_mode')).toBe('pro');
  });

  it('setMode("noob") flips the signal and persists', () => {
    const service = createService();
    service.setMode('pro');
    service.setMode('noob');
    expect(service.mode()).toBe('noob');
    expect(localStorage.getItem('xfil_operator_mode')).toBe('noob');
  });

  it('toggle() flips noob → pro → noob', () => {
    const service = createService();
    expect(service.mode()).toBe('noob');
    service.toggle();
    expect(service.mode()).toBe('pro');
    service.toggle();
    expect(service.mode()).toBe('noob');
  });
});
