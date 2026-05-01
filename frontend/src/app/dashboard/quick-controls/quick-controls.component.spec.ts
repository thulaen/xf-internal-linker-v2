import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { QuickControlsComponent } from './quick-controls.component';
import {
  RuntimeModelsService,
  RuntimeModelsSummary,
} from '../../admin-models/runtime-models.service';

const baseSummary: RuntimeModelsSummary = {
  task_type: 'embedding',
  active_model: {
    id: 1,
    task_type: 'embedding',
    model_name: 'BAAI/bge-m3',
    model_family: 'sentence-transformers',
    dimension: 1024,
    device_target: 'cpu',
    batch_size: 32,
    memory_profile: {},
    role: 'champion',
    status: 'ready',
    health_result: {},
    algorithm_version: 'fr020-v1',
    promoted_at: null,
    draining_since: null,
    last_warmup_result: {},
  },
  candidate_model: null,
  placements: [],
  reclaimable_disk_bytes: 0,
  backfill: null,
  device: 'cpu',
  hot_swap_safe: true,
  master_paused: false,
  recent_audit_log: [],
  last_audit_at: null,
};

function render(summary: RuntimeModelsSummary) {
  return TestBed.configureTestingModule({
    imports: [QuickControlsComponent, NoopAnimationsModule],
    providers: [
      {
        provide: RuntimeModelsService,
        useValue: {
          list: () => of(summary),
          action: () => of({ status: 'ok' }),
        },
      },
    ],
  })
    .compileComponents()
    .then(() => {
      const fixture = TestBed.createComponent(QuickControlsComponent);
      fixture.detectChanges();
      return fixture;
    });
}

describe('QuickControlsComponent', () => {
  it('shows Pause when runtime work is not globally paused', async () => {
    const fixture = await render(baseSummary);
    const text = fixture.nativeElement.textContent;

    expect(text).toContain('Pause');
    expect(text).not.toContain('Resume');
  });

  it('shows Resume when runtime work is globally paused', async () => {
    const fixture = await render({ ...baseSummary, master_paused: true });
    const text = fixture.nativeElement.textContent;

    expect(text).toContain('Resume');
    expect(text).not.toContain('Pause');
  });
});
