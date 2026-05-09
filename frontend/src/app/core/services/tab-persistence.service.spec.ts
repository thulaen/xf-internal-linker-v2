import { TestBed } from '@angular/core/testing';
import { TabPersistenceService } from './tab-persistence.service';

describe('TabPersistenceService', () => {
  let service: TabPersistenceService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(TabPersistenceService);
    localStorage.clear();
  });

  afterEach(() => localStorage.clear());

  it('read() returns the fallback when no value is stored', () => {
    expect(service.read('settings.foo')).toBe(0);
    expect(service.read('settings.foo', 7)).toBe(7);
  });

  it('write() then read() returns the same index', () => {
    service.write('settings.foo', 3);
    expect(service.read('settings.foo')).toBe(3);
  });

  it('write() namespaces the key under tabprefs.', () => {
    service.write('settings.foo', 2);
    expect(localStorage.getItem('tabprefs.settings.foo')).toBe('2');
  });

  it('write() rejects non-finite or negative indexes', () => {
    service.write('a', Number.NaN);
    service.write('a', -1);
    service.write('a', Infinity);
    expect(localStorage.getItem('tabprefs.a')).toBeNull();
  });

  it('read() falls back when stored value parses to NaN', () => {
    localStorage.setItem('tabprefs.bad', 'not-a-number');
    expect(service.read('bad', 5)).toBe(5);
  });

  it('read() falls back when stored value is negative', () => {
    localStorage.setItem('tabprefs.neg', '-1');
    expect(service.read('neg', 4)).toBe(4);
  });

  it('clear() removes only the requested key', () => {
    service.write('a', 1);
    service.write('b', 2);
    service.clear('a');
    expect(service.read('a')).toBe(0);
    expect(service.read('b')).toBe(2);
  });

  it('clearAll() removes every tabprefs.* entry but leaves unrelated keys', () => {
    service.write('a', 1);
    service.write('b', 2);
    localStorage.setItem('unrelated', 'keep');
    service.clearAll();
    expect(service.read('a')).toBe(0);
    expect(service.read('b')).toBe(0);
    expect(localStorage.getItem('unrelated')).toBe('keep');
  });
});
