import { TestBed } from '@angular/core/testing';
import { DensityService } from './density.service';

describe('DensityService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-density');
  });

  function createService(): DensityService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(DensityService);
  }

  it('defaults to "comfortable" when localStorage is empty', () => {
    const service = createService();
    expect(service.density()).toBe('comfortable');
  });

  it('reads a previously-stored level back from localStorage', () => {
    localStorage.setItem('xfil_density', 'compact');
    const service = createService();
    expect(service.density()).toBe('compact');
  });

  it('ignores an invalid stored value and falls back to "comfortable"', () => {
    localStorage.setItem('xfil_density', 'gigantic');
    const service = createService();
    expect(service.density()).toBe('comfortable');
  });

  it('set() updates the signal and persists the value', () => {
    const service = createService();
    service.set('spacious');
    expect(service.density()).toBe('spacious');
    expect(localStorage.getItem('xfil_density')).toBe('spacious');
  });

  it('set() rejects unknown levels (no signal update, no persistence)', () => {
    const service = createService();
    service.set('huge' as never);
    expect(service.density()).toBe('comfortable');
    expect(localStorage.getItem('xfil_density')).toBeNull();
  });

  // The effect() that mirrors density onto <html data-density="..."> is
  // not asserted here because Angular signal effects don't run inside
  // plain TestBed without ApplicationRef.tick() and the harness setup
  // for that adds noise without testing logic this service owns.
  // The mirroring is exercised end-to-end at the app level.
});
