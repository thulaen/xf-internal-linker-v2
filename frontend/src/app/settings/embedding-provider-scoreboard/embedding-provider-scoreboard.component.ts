import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  OnInit,
  inject,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  EmbeddingProviderScore,
  EmbeddingProviderScoreRun,
  SiloSettingsService,
} from '../silo-settings.service';

@Component({
  selector: 'app-embedding-provider-scoreboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './embedding-provider-scoreboard.component.html',
  styleUrls: ['./embedding-provider-scoreboard.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmbeddingProviderScoreboardComponent implements OnInit {
  private readonly service = inject(SiloSettingsService);
  private readonly snack = inject(MatSnackBar);
  private readonly cdr = inject(ChangeDetectorRef);

  runs: EmbeddingProviderScoreRun[] = [];
  loading = true;
  starting = false;
  costConfirmed = false;
  sampleSize = 1000;
  error = '';

  ngOnInit(): void {
    this.loadRuns();
  }

  loadRuns(): void {
    this.loading = true;
    this.error = '';
    this.service.listEmbeddingProviderScoreRuns()
      .pipe(finalize(() => {
        this.loading = false;
        this.cdr.markForCheck();
      }))
      .subscribe({
        next: (response) => {
          this.runs = response.runs;
          this.cdr.markForCheck();
        },
        error: () => {
          this.error = 'Provider scores could not be loaded.';
          this.cdr.markForCheck();
        },
      });
  }

  startRun(): void {
    if (!this.costConfirmed || this.starting) {
      return;
    }
    this.starting = true;
    this.service.startEmbeddingProviderScoreRun(this.sampleSize)
      .pipe(finalize(() => {
        this.starting = false;
        this.cdr.markForCheck();
      }))
      .subscribe({
        next: () => {
          this.costConfirmed = false;
          this.snack.open('Provider score run started.', 'OK', { duration: 2500 });
          this.loadRuns();
        },
        error: () => {
          this.error = 'Provider score run could not be started.';
          this.cdr.markForCheck();
        },
      });
  }

  unban(provider: EmbeddingProviderScore): void {
    this.service.unbanEmbeddingProvider(provider.provider).subscribe({
      next: () => {
        provider.is_banned = false;
        this.snack.open(`${provider.provider} is unbanned.`, 'OK', { duration: 2500 });
        this.cdr.markForCheck();
      },
      error: () => {
        this.error = `${provider.provider} could not be unbanned.`;
        this.cdr.markForCheck();
      },
    });
  }

  metric(value: number | null): string {
    return value === null ? 'not measured' : value.toFixed(3);
  }
}
