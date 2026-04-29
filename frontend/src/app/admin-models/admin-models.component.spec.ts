/**
 * Smoke spec for the AdminModelsComponent (Group M.1).
 *
 * Three thin tests: empty-registry path renders the inventory empty
 * state, populated-registry path renders a champion card + action
 * buttons, and a failed list call renders the error card with a
 * working retry button. Mock the service so no HTTP fires.
 */
import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of, throwError } from 'rxjs';

import { AdminModelsComponent } from './admin-models.component';
import {
  RuntimeModelsService,
  RuntimeModelsSummary,
} from './runtime-models.service';

const emptySummary: RuntimeModelsSummary = {
  task_type: 'embedding',
  active_model: null,
  candidate_model: null,
  placements: [],
  reclaimable_disk_bytes: 0,
  backfill: null,
  device: 'cpu',
  hot_swap_safe: true,
  recent_audit_log: [],
  last_audit_at: null,
};

const populatedSummary: RuntimeModelsSummary = {
  ...emptySummary,
  active_model: {
    id: 1,
    task_type: 'embedding',
    model_name: 'BAAI/bge-m3',
    model_family: 'sentence-transformers',
    dimension: 1024,
    device_target: 'cuda',
    batch_size: 32,
    memory_profile: {},
    role: 'champion',
    status: 'ready',
    health_result: {},
    algorithm_version: 'fr020-v1',
    promoted_at: '2026-04-20T12:00:00Z',
    draining_since: null,
    last_warmup_result: {},
  },
};

describe('AdminModelsComponent', () => {
  it('renders the empty-registry state', async () => {
    await TestBed.configureTestingModule({
      imports: [AdminModelsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: RuntimeModelsService,
          useValue: { list: () => of(emptySummary) },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AdminModelsComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('No embedding models registered yet.');
  });

  it('renders the champion card + action buttons when a model is registered', async () => {
    await TestBed.configureTestingModule({
      imports: [AdminModelsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: RuntimeModelsService,
          useValue: { list: () => of(populatedSummary) },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AdminModelsComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Champion');
    expect(text).toContain('BAAI/bge-m3');
    expect(text).toContain('Pause');
    expect(text).toContain('Resume');
    expect(text).toContain('Drain');
  });

  it('renders the error card when the list call fails', async () => {
    await TestBed.configureTestingModule({
      imports: [AdminModelsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: RuntimeModelsService,
          useValue: {
            list: () =>
              throwError(() => ({ error: { error: 'simulated failure' } })),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AdminModelsComponent);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Could not load the model registry.');
    expect(text).toContain('simulated failure');
    expect(text).toContain('Retry');
  });
});
