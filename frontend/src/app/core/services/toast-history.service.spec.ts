import { TestBed } from '@angular/core/testing';
import { ToastHistoryService } from './toast-history.service';

describe('ToastHistoryService', () => {
  let service: ToastHistoryService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ToastHistoryService);
  });

  it('starts empty', () => {
    expect(service.entries()).toEqual([]);
  });

  it('record() prepends a new entry (newest first)', () => {
    service.record('first');
    service.record('second');
    const entries = service.entries();
    expect(entries.length).toBe(2);
    expect(entries[0].message).toBe('second');
    expect(entries[1].message).toBe('first');
  });

  it('record() defaults severity to "info"', () => {
    const r = service.record('hello');
    expect(r.severity).toBe('info');
  });

  it('record() respects an explicit severity', () => {
    const r = service.record('uh oh', 'error');
    expect(r.severity).toBe('error');
  });

  it('record() returns an entry with id, message, severity, and timestamp', () => {
    const r = service.record('m', 'warning');
    expect(r.id).toMatch(/^toast-/);
    expect(r.message).toBe('m');
    expect(r.severity).toBe('warning');
    expect(typeof r.at).toBe('number');
  });

  it('record() trims the history to 50 entries', () => {
    for (let i = 0; i < 60; i++) service.record(`m${i}`);
    expect(service.entries().length).toBe(50);
    // The newest 50 are kept (m59 → m10), oldest dropped.
    expect(service.entries()[0].message).toBe('m59');
    expect(service.entries()[49].message).toBe('m10');
  });

  it('clear() empties the history', () => {
    service.record('x');
    service.record('y');
    service.clear();
    expect(service.entries()).toEqual([]);
  });
});
