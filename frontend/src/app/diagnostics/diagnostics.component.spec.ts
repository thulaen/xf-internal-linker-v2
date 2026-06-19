import { Component, EventEmitter, Input, Output, ChangeDetectionStrategy } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute } from '@angular/router';
import { EMPTY, of } from 'rxjs';

import { VisibilityGateService } from '../core/util/visibility-gate.service';
import { GlitchtipService } from '../core/services/glitchtip.service';
import { RealtimeService } from '../core/services/realtime.service';
import { ScrollAttentionService } from '../core/services/scroll-attention.service';
import { ConflictListComponent } from './conflict-list/conflict-list.component';
import { DiagnosticsComponent } from './diagnostics.component';
import { DiagnosticsService, WeightDiagnosticsResponse, WeightSignal } from './diagnostics.service';
import { AccuracyLabCardComponent } from './accuracy-lab-card/accuracy-lab-card.component';
import { ReadinessMatrixComponent } from './readiness-matrix/readiness-matrix.component';
import { ServiceCardComponent } from './service-card/service-card.component';
import { SuppressedPairsCardComponent } from './suppressed-pairs-card/suppressed-pairs-card.component';

@Component({
  selector: 'app-service-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
class MockServiceCardComponent {
  @Input() service: unknown;
}

@Component({
  selector: 'app-conflict-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
class MockConflictListComponent {
  @Input() conflicts: unknown[] = [];
  @Output() resolve = new EventEmitter<unknown>();
}

@Component({
  selector: 'app-readiness-matrix',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
class MockReadinessMatrixComponent {
  @Input() features: unknown[] = [];
}

@Component({
  selector: 'app-accuracy-lab-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
class MockAccuracyLabCardComponent {}

@Component({
  selector: 'app-suppressed-pairs-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
class MockSuppressedPairsCardComponent {}

const WAVE2_IDS = ['passage_relevance', 'darb', 'kmig', 'tapb', 'kcib', 'berp', 'hgte', 'rsqva'];

function weightSignal(id: string): WeightSignal {
  return {
    id,
    name: id === 'passage_relevance' ? 'Passage-Level Relevance' : id.toUpperCase(),
    type: 'ranking',
    description: `Plain-English description for ${id}.`,
    weight: 0.05,
    cpp_acceleration: {
      active: false,
      status_label: 'Not Supported',
      kernel: null,
    },
    storage: {
      table: 'suggestions_suggestion',
      row_count: 2,
      size_bytes: 0,
      size_human: '0.0 B',
    },
    health: {
      status: 'healthy',
      recent_errors: 0,
    },
    system_health: {
      window_days: 7,
      sample_count: 2,
      neutral_fallback_count: 1,
      neutral_fallback_rate: 0.5,
      last_run_at: '2026-04-29T12:00:00Z',
      status_label: 'Fallbacks seen',
      plain_english: '1 of 2 recent diagnostics used the neutral fallback.',
    },
    governance: {
      status: 'active',
      fr_id: id === 'passage_relevance' ? 'FR-053' : 'FR-099',
      spec_path: `docs/specs/${id}.md`,
      academic_source: 'Source-backed spec',
      source_kind: 'paper',
      architecture_lane: 'python_only',
      neutral_value: 0,
      min_data_threshold: '>=1 row',
      diagnostic_surfaces: ['system_health'],
      benchmark_module: null,
      autotune_included: true,
      default_enabled: true,
      added_in_phase: 'test',
    },
  };
}

describe('DiagnosticsComponent', () => {
  it('renders all eight Wave-2 model health cards with View spec buttons', async () => {
    const weightDiagnostics: WeightDiagnosticsResponse = {
      signals: WAVE2_IDS.map(weightSignal),
      summary: {
        total_signals: WAVE2_IDS.length,
        cpp_accelerated_count: 0,
        healthy_count: WAVE2_IDS.length,
        last_refreshed: '2026-04-29T12:00:00Z',
      },
    };

    TestBed.overrideComponent(DiagnosticsComponent, {
      remove: {
        imports: [
          ServiceCardComponent,
          ConflictListComponent,
          ReadinessMatrixComponent,
          AccuracyLabCardComponent,
          SuppressedPairsCardComponent,
        ],
      },
      add: {
        imports: [
          MockServiceCardComponent,
          MockConflictListComponent,
          MockReadinessMatrixComponent,
          MockAccuracyLabCardComponent,
          MockSuppressedPairsCardComponent,
        ],
      },
    });

    await TestBed.configureTestingModule({
      imports: [DiagnosticsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: DiagnosticsService,
          useValue: {
            getServices: () => of([]),
            getConflicts: () => of([]),
            getFeatures: () => of([]),
            getResources: () => of(null),
            getErrors: () => of([]),
            getRuntimeContext: () => of(null),
            getNodes: () => of([]),
            getPipelineGate: () => of(null),
            getNdcgEval: () => of(null),
            getWeightDiagnostics: () => of(weightDiagnostics),
            refreshServices: () => of([]),
            detectConflicts: () => of([]),
          },
        },
        { provide: GlitchtipService, useValue: { getRecentEvents: () => of([]) } },
        { provide: RealtimeService, useValue: { subscribeTopic: () => EMPTY } },
        { provide: ScrollAttentionService, useValue: { drawTo: () => undefined } },
        { provide: MatSnackBar, useValue: { open: () => undefined } },
        { provide: MatDialog, useValue: { open: () => undefined } },
        { provide: VisibilityGateService, useValue: { whileLoggedInAndVisible: () => EMPTY } },
        { provide: ActivatedRoute, useValue: { fragment: EMPTY } },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(DiagnosticsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    for (const id of WAVE2_IDS) {
      const signal = weightSignal(id);
      expect(text).toContain(signal.name);
    }
    expect(fixture.nativeElement.querySelectorAll('.wave2-signal-card').length).toBe(8);
    expect(text.match(/View spec/g)?.length).toBe(8);
  });
});
