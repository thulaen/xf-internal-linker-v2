import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, interval, of, startWith, switchMap } from 'rxjs';

import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { PeHelperDirective } from '../shared/directives/pe-helper.directive';
import { WorkQueueOverview, WorkQueueService } from './work-queue.service';

@Component({
  selector: 'app-work-queue',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    PeHelperDirective,
  ],
  templateUrl: './work-queue.component.html',
  styleUrls: ['./work-queue.component.scss'],
})
export class WorkQueueComponent implements OnInit {
  readonly overview = signal<WorkQueueOverview | null>(null);
  readonly error = signal<string | null>(null);

  private readonly workQueue = inject(WorkQueueService);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    interval(15_000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.workQueue.overview().pipe(
            catchError((err) => {
              this.error.set(this.errorText(err));
              return of(null);
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((overview) => {
        if (overview) {
          this.overview.set(overview);
          this.error.set(null);
        }
      });
  }

  private errorText(err: unknown): string {
    if (err instanceof Error) return err.message;
    return 'Could not refresh the work queue.';
  }
}

