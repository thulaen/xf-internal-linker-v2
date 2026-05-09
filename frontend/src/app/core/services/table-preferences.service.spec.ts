import { TestBed } from '@angular/core/testing';
import { TablePreferencesService } from './table-preferences.service';

interface AlertPrefs extends Record<string, unknown> {
  sortActive?: string;
  sortDir?: 'asc' | 'desc';
  pageSize?: number;
  hiddenColumns?: string[];
}

describe('TablePreferencesService', () => {
  let service: TablePreferencesService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    service = TestBed.inject(TablePreferencesService);
  });

  afterEach(() => localStorage.clear());

  it('load() returns null when nothing is stored', () => {
    expect(service.load<AlertPrefs>('alerts')).toBeNull();
  });

  it('save() then load() round-trips the prefs object', () => {
    service.save<AlertPrefs>('alerts', { pageSize: 25, sortDir: 'asc' });
    const loaded = service.load<AlertPrefs>('alerts');
    expect(loaded?.pageSize).toBe(25);
    expect(loaded?.sortDir).toBe('asc');
  });

  it('save() merges with existing prefs (partial updates preserve other keys)', () => {
    service.save<AlertPrefs>('alerts', { pageSize: 10, sortDir: 'asc' });
    service.save<AlertPrefs>('alerts', { sortDir: 'desc' });
    const loaded = service.load<AlertPrefs>('alerts');
    expect(loaded?.pageSize).toBe(10);
    expect(loaded?.sortDir).toBe('desc');
  });

  it('save() namespaces the key under tbl_prefs_*', () => {
    service.save<AlertPrefs>('alerts', { pageSize: 50 });
    expect(localStorage.getItem('tbl_prefs_alerts')).toContain('50');
  });

  it('load() returns null when stored value is corrupt JSON', () => {
    localStorage.setItem('tbl_prefs_bad', '{not json');
    expect(service.load<AlertPrefs>('bad')).toBeNull();
  });

  it('clear(tableId) removes only that one entry', () => {
    service.save<AlertPrefs>('alerts', { pageSize: 25 });
    service.save<AlertPrefs>('jobs', { pageSize: 50 });
    service.clear('alerts');
    expect(service.load<AlertPrefs>('alerts')).toBeNull();
    expect(service.load<AlertPrefs>('jobs')?.pageSize).toBe(50);
  });

  it('clearAll() removes every tbl_prefs_* entry but leaves unrelated keys', () => {
    service.save<AlertPrefs>('alerts', { pageSize: 25 });
    service.save<AlertPrefs>('jobs', { pageSize: 50 });
    localStorage.setItem('unrelated', 'keep');
    service.clearAll();
    expect(service.load<AlertPrefs>('alerts')).toBeNull();
    expect(service.load<AlertPrefs>('jobs')).toBeNull();
    expect(localStorage.getItem('unrelated')).toBe('keep');
  });
});
