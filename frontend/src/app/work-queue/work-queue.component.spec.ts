import { TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { WorkQueueComponent } from './work-queue.component';
import { WorkQueueOverview, WorkQueueService } from './work-queue.service';

describe('WorkQueueComponent', () => {
  const makeOverview = (overrides: Partial<WorkQueueOverview> = {}): WorkQueueOverview => ({
    as_of: '2026-06-03T09:00:00Z',
    now: [],
    blocked: [],
    self_healing: { status: 'ok', backend_health: 'up', frontend_health: 'up', reason: 'All good' },
    live_signals: { stale_evidence_count: 0, contradiction_count: 0, source_confidence: [] },
    agent_claims: [],
    cause_groups: [],
    real_time_topics: [],
    ...overrides,
  });

  function configure(overviewSpy: Spy): void {
    TestBed.configureTestingModule({
      imports: [WorkQueueComponent, NoopAnimationsModule],
      providers: [
        provideRouter([]),
        {
          provide: WorkQueueService,
          useValue: { overview: overviewSpy },
        },
      ],
    });
  }

  it('renders the now/blocked sections from the polled overview', fakeAsync(() => {
    const overview = makeOverview({
      now: [
        {
          key: 'autoissue:1',
          kind: 'autoissue',
          id: 1,
          title: 'Fix the importer',
          source: 'agent',
          severity: 'high',
          status: 'open',
          priority_score: 9,
          updated_at: null,
          affected_files: [],
          blocked: false,
          business_impact: 'Imports fail',
          next_action: 'Patch the parser',
        },
      ],
    });
    configure(vi.fn().mockReturnValue(of(overview)));
    const fixture = TestBed.createComponent(WorkQueueComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(fixture.componentInstance.overview()?.now.length).toBe(1);
    expect(fixture.nativeElement.querySelector('#work-queue-now')).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Fix the importer');
    expect(fixture.componentInstance.error()).toBeNull();

    fixture.destroy();
    discardPeriodicTasks();
  }));

  it('surfaces a plain-English error message when the overview request fails', fakeAsync(() => {
    configure(
      vi.fn().mockReturnValue(throwError(() => new Error('boom'))),
    );
    const fixture = TestBed.createComponent(WorkQueueComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(fixture.componentInstance.error()).toBe('boom');
    expect(fixture.componentInstance.overview()).toBeNull();

    fixture.destroy();
    discardPeriodicTasks();
  }));

  it('uses a generic fallback message for non-Error failures', fakeAsync(() => {
    configure(vi.fn().mockReturnValue(throwError(() => 'nope')));
    const fixture = TestBed.createComponent(WorkQueueComponent);
    fixture.detectChanges();
    tick();
    fixture.detectChanges();

    expect(fixture.componentInstance.error()).toBe('Could not refresh the work queue.');

    fixture.destroy();
    discardPeriodicTasks();
  }));
});
