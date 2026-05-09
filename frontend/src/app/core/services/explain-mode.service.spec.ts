import { TestBed } from '@angular/core/testing';
import { ExplainModeService } from './explain-mode.service';

describe('ExplainModeService', () => {
  beforeEach(() => localStorage.clear());

  function createService(): ExplainModeService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(ExplainModeService);
  }

  it('defaults to false on a fresh install', () => {
    const service = createService();
    expect(service.enabled()).toBe(false);
  });

  it('rehydrates "1" from localStorage as true', () => {
    localStorage.setItem('xfil_explain_mode', '1');
    const service = createService();
    expect(service.enabled()).toBe(true);
  });

  it('rehydrates anything other than "1" as false', () => {
    localStorage.setItem('xfil_explain_mode', 'true');
    const service = createService();
    expect(service.enabled()).toBe(false);
  });

  it('setEnabled(true) updates the signal and persists "1"', () => {
    const service = createService();
    service.setEnabled(true);
    expect(service.enabled()).toBe(true);
    expect(localStorage.getItem('xfil_explain_mode')).toBe('1');
  });

  it('setEnabled(false) updates the signal and persists "0"', () => {
    const service = createService();
    service.setEnabled(true);
    service.setEnabled(false);
    expect(service.enabled()).toBe(false);
    expect(localStorage.getItem('xfil_explain_mode')).toBe('0');
  });

  it('toggle() flips the current state', () => {
    const service = createService();
    expect(service.enabled()).toBe(false);
    service.toggle();
    expect(service.enabled()).toBe(true);
    service.toggle();
    expect(service.enabled()).toBe(false);
  });

  // toObservable() emits asynchronously after the next microtask within
  // an injection context — the harness setup needed to subscribe to it
  // reliably is heavier than the value of testing a 1-line wrapper.
  // The signal-based assertions above already cover the same logic.
});
