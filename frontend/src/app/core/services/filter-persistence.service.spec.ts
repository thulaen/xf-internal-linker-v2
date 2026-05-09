import { TestBed } from '@angular/core/testing';
import { FilterPersistenceService } from './filter-persistence.service';

describe('FilterPersistenceService', () => {
  let service: FilterPersistenceService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    service = TestBed.inject(FilterPersistenceService);
  });

  afterEach(() => localStorage.clear());

  it('read() returns the fallback when nothing is stored', () => {
    expect(service.read('alerts')).toBeNull();
    expect(service.read('alerts', { default: true })).toEqual({ default: true });
  });

  it('write() then read() round-trips the snapshot', () => {
    service.write('alerts', { severity: 'high' });
    expect(service.read<{ severity: string }>('alerts')).toEqual({ severity: 'high' });
  });

  it('write() namespaces the key under filterprefs.*', () => {
    service.write('alerts', { x: 1 });
    expect(localStorage.getItem('filterprefs.alerts')).toContain('"x":1');
  });

  it('read() returns the fallback when stored value is corrupt JSON', () => {
    localStorage.setItem('filterprefs.bad', '{not json');
    expect(service.read('bad', 'fallback')).toBe('fallback');
  });

  it('clear() removes the stored snapshot for that page', () => {
    service.write('alerts', { a: 1 });
    service.clear('alerts');
    expect(service.read('alerts')).toBeNull();
  });

  it('subscribe() returns an unsubscribe function', () => {
    const unsub = service.subscribe('alerts', () => undefined);
    expect(typeof unsub).toBe('function');
    expect(() => unsub()).not.toThrow();
  });

  it('subscribe() calls listeners when a storage event fires for the same pageId', () => {
    const calls: unknown[] = [];
    service.subscribe('alerts', (payload) => calls.push(payload));
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.alerts',
        newValue: JSON.stringify({ severity: 'low' }),
      }),
    );
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({ severity: 'low' });
  });

  it('subscribe() ignores storage events for unrelated keys', () => {
    const calls: unknown[] = [];
    service.subscribe('alerts', (payload) => calls.push(payload));
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'other.something',
        newValue: 'noise',
      }),
    );
    expect(calls.length).toBe(0);
  });

  it('subscribe() ignores storage events for a different pageId', () => {
    const calls: unknown[] = [];
    service.subscribe('alerts', (payload) => calls.push(payload));
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.jobs',
        newValue: JSON.stringify({}),
      }),
    );
    expect(calls.length).toBe(0);
  });

  it('subscribe() decodes payload as null when newValue is missing', () => {
    let received: unknown = 'not-set';
    service.subscribe('alerts', (payload) => (received = payload));
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.alerts',
        newValue: null,
      }),
    );
    expect(received).toBeNull();
  });

  it('subscribe() decodes payload as null when newValue is invalid JSON', () => {
    let received: unknown = 'not-set';
    service.subscribe('alerts', (payload) => (received = payload));
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.alerts',
        newValue: '{not json',
      }),
    );
    expect(received).toBeNull();
  });

  it('subscribe() shields siblings from a listener that throws', () => {
    let bSawIt = false;
    service.subscribe('alerts', () => {
      throw new Error('first listener boom');
    });
    service.subscribe('alerts', () => {
      bSawIt = true;
    });
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.alerts',
        newValue: '{}',
      }),
    );
    expect(bSawIt).toBe(true);
  });

  it('unsubscribe() removes the listener', () => {
    const calls: unknown[] = [];
    const unsub = service.subscribe('alerts', (payload) => calls.push(payload));
    unsub();
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'filterprefs.alerts',
        newValue: '{}',
      }),
    );
    expect(calls.length).toBe(0);
  });
});
