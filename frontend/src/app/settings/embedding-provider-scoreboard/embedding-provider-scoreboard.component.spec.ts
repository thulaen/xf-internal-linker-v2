import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';

import { EmbeddingProviderScoreboardComponent } from './embedding-provider-scoreboard.component';
import { SiloSettingsService } from '../silo-settings.service';

describe('EmbeddingProviderScoreboardComponent', () => {
  let component: EmbeddingProviderScoreboardComponent;
  let service: {
    listEmbeddingProviderScoreRuns: ReturnType<typeof vi.fn>;
    startEmbeddingProviderScoreRun: ReturnType<typeof vi.fn>;
    unbanEmbeddingProvider: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    service = {
      listEmbeddingProviderScoreRuns: vi.fn().mockReturnValue(of({ runs: [] })),
      startEmbeddingProviderScoreRun: vi.fn().mockReturnValue(of({ task_id: 'task-1', sample_size: 10 })),
      unbanEmbeddingProvider: vi.fn().mockReturnValue(of({ provider: 'gemini', is_banned: false })),
    };

    await TestBed.configureTestingModule({
      imports: [EmbeddingProviderScoreboardComponent],
      providers: [
        { provide: SiloSettingsService, useValue: service },
        { provide: MatSnackBar, useValue: { open: () => undefined } },
      ],
    }).compileComponents();

    component = TestBed.createComponent(EmbeddingProviderScoreboardComponent).componentInstance;
  });

  it('loads runs on demand', () => {
    component.loadRuns();
    expect(service.listEmbeddingProviderScoreRuns).toHaveBeenCalled();
    expect(component.loading).toBeFalsy();
  });

  it('does not start a run without cost confirmation', () => {
    component.startRun();
    expect(service.startEmbeddingProviderScoreRun).not.toHaveBeenCalled();
  });

  it('starts a run when cost is confirmed', () => {
    component.costConfirmed = true;
    component.sampleSize = 10;
    component.startRun();
    expect(service.startEmbeddingProviderScoreRun).toHaveBeenCalledWith(10);
    expect(component.costConfirmed).toBeFalsy();
  });

  it('sets an error when loading fails', () => {
    service.listEmbeddingProviderScoreRuns.mockReturnValue(throwError(() => new Error('nope')));
    component.loadRuns();
    expect(component.error).toBe('Provider scores could not be loaded.');
  });

  it('formats missing metrics in plain English', () => {
    expect(component.metric(null)).toBe('not measured');
    expect(component.metric(0.1234)).toBe('0.123');
  });
});
