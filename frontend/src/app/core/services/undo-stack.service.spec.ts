import { TestBed } from '@angular/core/testing';
import { UndoStackService } from './undo-stack.service';

describe('UndoStackService', () => {
  let service: UndoStackService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(UndoStackService);
  });

  it('starts empty', () => {
    expect(service.count()).toBe(0);
    expect(service.top()).toBeNull();
    expect(service.entries()).toEqual([]);
  });

  it('push() adds an entry and returns it', () => {
    const action = service.push('Deleted x', () => undefined);
    expect(service.count()).toBe(1);
    expect(action.label).toBe('Deleted x');
    expect(action.id).toMatch(/^undo-/);
    expect(typeof action.createdAt).toBe('number');
    expect(action.expiresAt).toBeGreaterThan(action.createdAt);
  });

  it('push() respects custom ttlMs', () => {
    const action = service.push('foo', () => undefined, { ttlMs: 1000 });
    expect(action.expiresAt - action.createdAt).toBe(1000);
  });

  it('push() persists optional tag', () => {
    const action = service.push('foo', () => undefined, { tag: 'review' });
    expect(action.tag).toBe('review');
  });

  it('top() returns the most-recently-pushed entry', () => {
    service.push('first', () => undefined);
    const second = service.push('second', () => undefined);
    expect(service.top()?.id).toBe(second.id);
  });

  it('entries() returns newest-first', () => {
    service.push('a', () => undefined);
    service.push('b', () => undefined);
    service.push('c', () => undefined);
    expect(service.entries().map((e) => e.label)).toEqual(['c', 'b', 'a']);
  });

  it('push() trims oldest when the stack exceeds 5 entries', () => {
    for (const label of ['a', 'b', 'c', 'd', 'e', 'f']) {
      service.push(label, () => undefined);
    }
    expect(service.count()).toBe(5);
    expect(service.entries().map((e) => e.label)).toEqual(['f', 'e', 'd', 'c', 'b']);
  });

  it('undoTop() runs the reverse fn and removes the entry', async () => {
    const reverse = jasmine.createSpy('reverse');
    service.push('x', reverse);
    const undone = await service.undoTop();
    expect(reverse).toHaveBeenCalledTimes(1);
    expect(undone?.label).toBe('x');
    expect(service.count()).toBe(0);
  });

  it('undoTop() returns null when the stack is empty', async () => {
    expect(await service.undoTop()).toBeNull();
  });

  it('undoTop() awaits async reverse fns', async () => {
    let resolved = false;
    service.push('async', async () => {
      await new Promise<void>((r) => setTimeout(r, 0));
      resolved = true;
    });
    await service.undoTop();
    expect(resolved).toBe(true);
  });

  it('undoTop() removes the entry even when reverse throws', async () => {
    service.push('boom', () => {
      throw new Error('oops');
    });
    await service.undoTop();
    expect(service.count()).toBe(0);
  });

  it('undoTop() removes the entry even when async reverse rejects', async () => {
    service.push('boom', () => Promise.reject(new Error('oops')));
    await service.undoTop();
    expect(service.count()).toBe(0);
  });

  it('undoById() targets a specific entry', async () => {
    const a = service.push('a', () => undefined);
    const b = service.push('b', () => undefined);
    const undone = await service.undoById(a.id);
    expect(undone?.id).toBe(a.id);
    expect(service.count()).toBe(1);
    expect(service.top()?.id).toBe(b.id);
  });

  it('undoById() returns null for an unknown id', async () => {
    service.push('a', () => undefined);
    expect(await service.undoById('nope')).toBeNull();
    expect(service.count()).toBe(1);
  });

  it('clear() empties the stack', () => {
    service.push('a', () => undefined);
    service.push('b', () => undefined);
    service.clear();
    expect(service.count()).toBe(0);
  });

  it('purges expired entries on push()', () => {
    // Push an entry that expires immediately.
    const expired = service.push('old', () => undefined, { ttlMs: -1 });
    expect(service.count()).toBe(1);
    // Push a new entry — purge should drop the expired one.
    service.push('fresh', () => undefined);
    expect(service.count()).toBe(1);
    expect(service.top()?.label).toBe('fresh');
    expect(service.top()?.id).not.toBe(expired.id);
  });
});
