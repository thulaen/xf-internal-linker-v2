import { TestBed } from '@angular/core/testing';
import { CrossTabSyncService } from './cross-tab-sync.service';

describe('CrossTabSyncService', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({});
  });

  it('constructs without throwing in a normal browser environment', () => {
    expect(() => TestBed.inject(CrossTabSyncService)).not.toThrow();
  });

  it('exposes a messages$ observable that can be subscribed to', () => {
    const service = TestBed.inject(CrossTabSyncService);
    expect(service.messages$).toBeDefined();
    expect(typeof service.messages$.subscribe).toBe('function');
    const sub = service.messages$.subscribe();
    sub.unsubscribe();
  });

  it('emit() does not throw when called multiple times', () => {
    const service = TestBed.inject(CrossTabSyncService);
    expect(() => {
      service.emit('foo');
      service.emit('bar', { id: 1 });
      service.emit('baz', { nested: { value: 'x' } });
    }).not.toThrow();
  });
});
