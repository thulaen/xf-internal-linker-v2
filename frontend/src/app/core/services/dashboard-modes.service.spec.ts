import { TestBed } from '@angular/core/testing';
import { DashboardModesService } from './dashboard-modes.service';

describe('DashboardModesService', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  function createService(): DashboardModesService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(DashboardModesService);
  }

  it('safe + calm default to false on a fresh install', () => {
    const service = createService();
    expect(service.safe()).toBe(false);
    expect(service.calm()).toBe(false);
    expect(service.anyActive()).toBe(false);
  });

  it('rehydrates safe + calm from localStorage', () => {
    localStorage.setItem('xfil_safe_mode', '1');
    localStorage.setItem('xfil_calm_mode', '1');
    const service = createService();
    expect(service.safe()).toBe(true);
    expect(service.calm()).toBe(true);
    expect(service.anyActive()).toBe(true);
  });

  it('setSafe(true) flips the signal and persists "1"', () => {
    const service = createService();
    service.setSafe(true);
    expect(service.safe()).toBe(true);
    expect(localStorage.getItem('xfil_safe_mode')).toBe('1');
  });

  it('setSafe(false) flips the signal and persists "0"', () => {
    const service = createService();
    service.setSafe(true);
    service.setSafe(false);
    expect(service.safe()).toBe(false);
    expect(localStorage.getItem('xfil_safe_mode')).toBe('0');
  });

  it('toggleSafe() inverts the current state', () => {
    const service = createService();
    expect(service.safe()).toBe(false);
    service.toggleSafe();
    expect(service.safe()).toBe(true);
    service.toggleSafe();
    expect(service.safe()).toBe(false);
  });

  it('setCalm(true) flips the calm signal and persists', () => {
    const service = createService();
    service.setCalm(true);
    expect(service.calm()).toBe(true);
    expect(localStorage.getItem('xfil_calm_mode')).toBe('1');
  });

  it('toggleCalm() inverts the current state', () => {
    const service = createService();
    service.toggleCalm();
    expect(service.calm()).toBe(true);
    service.toggleCalm();
    expect(service.calm()).toBe(false);
  });

  it('anyActive is true when either flag is on', () => {
    const service = createService();
    expect(service.anyActive()).toBe(false);
    service.setSafe(true);
    expect(service.anyActive()).toBe(true);
    service.setSafe(false);
    expect(service.anyActive()).toBe(false);
    service.setCalm(true);
    expect(service.anyActive()).toBe(true);
  });
});
