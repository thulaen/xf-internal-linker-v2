import { TestBed } from '@angular/core/testing';
import { OnboardingStateService } from './onboarding-state.service';

describe('OnboardingStateService', () => {
  beforeEach(() => localStorage.clear());

  function createService(): OnboardingStateService {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(OnboardingStateService);
  }

  it('starts with an empty done-set', () => {
    const service = createService();
    expect(service.done().size).toBe(0);
  });

  it('rehydrates milestones from the onb.* namespace', () => {
    localStorage.setItem('onb.first-suggestion-approved', '1');
    localStorage.setItem('onb.discovered-calm-mode', '1');
    const service = createService();
    expect(service.isDone('first-suggestion-approved')).toBe(true);
    expect(service.isDone('discovered-calm-mode')).toBe(true);
    expect(service.done().size).toBe(2);
  });

  it('rehydrates legacy tour completions from the xfil_tour_completed.* namespace', () => {
    localStorage.setItem('xfil_tour_completed.dashboard-v1', '1');
    const service = createService();
    expect(service.isDone('dashboard-v1')).toBe(true);
  });

  it('skips localStorage entries with values other than "1"', () => {
    localStorage.setItem('onb.almost', 'true');
    const service = createService();
    expect(service.isDone('almost')).toBe(false);
  });

  it('markDone() persists, updates the signal, and is idempotent', () => {
    const service = createService();
    service.markDone('first-preference-visit');
    expect(service.isDone('first-preference-visit')).toBe(true);
    expect(localStorage.getItem('onb.first-preference-visit')).toBe('1');

    // Marking again should not duplicate or re-set.
    const sizeBefore = service.done().size;
    service.markDone('first-preference-visit');
    expect(service.done().size).toBe(sizeBefore);
  });

  it('reset(id) removes the milestone from both namespaces and the signal', () => {
    localStorage.setItem('xfil_tour_completed.dashboard-v1', '1');
    const service = createService();
    expect(service.isDone('dashboard-v1')).toBe(true);

    service.reset('dashboard-v1');
    expect(service.isDone('dashboard-v1')).toBe(false);
    expect(localStorage.getItem('xfil_tour_completed.dashboard-v1')).toBeNull();
  });

  it('reset(id) is a no-op when the id was not done', () => {
    const service = createService();
    service.reset('never-done');
    expect(service.done().size).toBe(0);
  });

  it('resetAll() wipes onb.* + xfil_tour_completed.* but preserves unrelated keys', () => {
    localStorage.setItem('onb.a', '1');
    localStorage.setItem('xfil_tour_completed.b', '1');
    localStorage.setItem('not-onboarding', 'keep');
    const service = createService();

    service.resetAll();
    expect(service.done().size).toBe(0);
    expect(localStorage.getItem('onb.a')).toBeNull();
    expect(localStorage.getItem('xfil_tour_completed.b')).toBeNull();
    expect(localStorage.getItem('not-onboarding')).toBe('keep');
  });

  it('allDone() returns true only when every requested id is done', () => {
    const service = createService();
    service.markDone('a');
    service.markDone('b');
    expect(service.allDone(['a', 'b'])).toBe(true);
    expect(service.allDone(['a', 'b', 'c'])).toBe(false);
    expect(service.allDone([])).toBe(true);
  });

  it('progress() returns 0/0/0 before a catalogue is registered', () => {
    const service = createService();
    expect(service.progress()).toEqual({ done: 0, total: 0, percent: 0 });
  });

  it('progress() returns done/total/percent against the registered catalogue', () => {
    const service = createService();
    service.registerCatalogue(['a', 'b', 'c', 'd']);
    service.markDone('a');
    service.markDone('b');
    expect(service.progress()).toEqual({ done: 2, total: 4, percent: 50 });
  });
});
