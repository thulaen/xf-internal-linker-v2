import { TestBed } from '@angular/core/testing';
import { RouteFavoritesService } from './route-favorites.service';

describe('RouteFavoritesService', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  function createService(): RouteFavoritesService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(RouteFavoritesService);
  }

  it('starts empty when localStorage has no entry', () => {
    const service = createService();
    expect(service.entries()).toEqual([]);
  });

  it('add() creates an entry with the supplied label + icon and persists', () => {
    const service = createService();
    const entry = service.add('/review', 'Review', 'rate_review');
    expect(entry).not.toBeNull();
    expect(entry!.url).toBe('/review');
    expect(entry!.label).toBe('Review');
    expect(entry!.icon).toBe('rate_review');
    expect(entry!.addedAt).toBeGreaterThan(0);
    expect(service.entries().length).toBe(1);
    expect(localStorage.getItem('favroutes.v1')).toContain('"url":"/review"');
  });

  it('add() defaults the icon to "star" when omitted or empty', () => {
    const service = createService();
    const a = service.add('/a', 'A');
    const b = service.add('/b', 'B', '');
    expect(a!.icon).toBe('star');
    expect(b!.icon).toBe('star');
  });

  it('add() de-duplicates and returns the existing entry instead of creating a new one', () => {
    const service = createService();
    const first = service.add('/dup', 'Dup');
    const second = service.add('/dup', 'Dup again');
    expect(first).toEqual(second!);
    expect(service.entries().length).toBe(1);
  });

  it('add() refuses past the 12-entry cap', () => {
    const service = createService();
    for (let i = 0; i < 12; i++) {
      expect(service.add(`/r${i}`, `R${i}`)).not.toBeNull();
    }
    expect(service.add('/overflow', 'X')).toBeNull();
    expect(service.entries().length).toBe(12);
  });

  it('isStarred() reflects current state', () => {
    const service = createService();
    expect(service.isStarred('/a')).toBe(false);
    service.add('/a', 'A');
    expect(service.isStarred('/a')).toBe(true);
  });

  it('toggle() adds when missing, removes when present, returns null on remove', () => {
    const service = createService();
    const added = service.toggle('/x', 'X');
    expect(added).not.toBeNull();
    expect(service.isStarred('/x')).toBe(true);

    const removed = service.toggle('/x', 'X');
    expect(removed).toBeNull();
    expect(service.isStarred('/x')).toBe(false);
  });

  it('remove() drops only the matching url and is a no-op when not present', () => {
    const service = createService();
    service.add('/a', 'A');
    service.add('/b', 'B');
    service.remove('/missing'); // no-op — should not change state
    expect(service.entries().length).toBe(2);
    service.remove('/a');
    expect(service.entries().map((e) => e.url)).toEqual(['/b']);
  });

  it('clear() empties the list and the persisted entry', () => {
    const service = createService();
    service.add('/a', 'A');
    service.clear();
    expect(service.entries()).toEqual([]);
    expect(localStorage.getItem('favroutes.v1')).toBe('[]');
  });

  it('rehydrates from a previously persisted list', () => {
    localStorage.setItem(
      'favroutes.v1',
      JSON.stringify([
        { url: '/r', label: 'Recent', icon: 'history', addedAt: 1 },
        { url: '/m', label: 'M', icon: 'star', addedAt: 2 },
      ]),
    );
    const service = createService();
    expect(service.entries().length).toBe(2);
    expect(service.entries()[0].url).toBe('/r');
  });

  it('falls back to [] when stored value is malformed JSON', () => {
    localStorage.setItem('favroutes.v1', '{not json');
    const service = createService();
    expect(service.entries()).toEqual([]);
  });

  it('falls back to [] when stored value is not an array', () => {
    localStorage.setItem('favroutes.v1', '{"x":1}');
    const service = createService();
    expect(service.entries()).toEqual([]);
  });

  it('drops malformed entries during rehydration', () => {
    localStorage.setItem(
      'favroutes.v1',
      JSON.stringify([
        { url: '/ok', label: 'OK', icon: 'star', addedAt: 1 },
        { not: 'a route' },
        null,
        { url: 123, label: 'bad' },
      ]),
    );
    const service = createService();
    expect(service.entries().length).toBe(1);
    expect(service.entries()[0].url).toBe('/ok');
  });
});
