import { ChangeDetectionStrategy, Component, DestroyRef, inject, OnInit, signal, computed } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin, of } from 'rxjs';
import { catchError, finalize } from 'rxjs/operators';
import {
  RuntimeModel,
  RuntimeModelsService,
  RuntimeModelAction,
  RuntimeModelStatus,
  RuntimeModelTaskType,
  RuntimeModelsSummary
} from '../../admin-models/runtime-models.service';

/** 
 * Status priority for sorting: 
 * 'ready' (Running/Ready) first, then 'paused', then everything else.
 */
const STATUS_PRIORITY: Record<string, number> = {
  'ready': 0,
  'warming': 1,
  'paused': 2,
  'downloading': 3,
  'registered': 4,
  'draining': 5,
  'failed': 6,
  'retired': 7
};

type QuickControlModel = RuntimeModel & {
  display_status: RuntimeModelStatus;
};

@Component({
  selector: 'app-quick-controls',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule
  ],
  templateUrl: './quick-controls.component.html',
  styleUrls: ['./quick-controls.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QuickControlsComponent implements OnInit {
  private readonly svc = inject(RuntimeModelsService);
  private readonly snack = inject(MatSnackBar);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal<boolean>(true);
  readonly error = signal<string>('');
  readonly summaries = signal<RuntimeModelsSummary[]>([]);
  readonly busyId = signal<string>('');

  /** 
   * Extract active (champion) models from all summaries, 
   * then sort by status priority, then name.
   */
  readonly activeModels = computed<QuickControlModel[]>(() => {
    const active = this.summaries()
      .map(s => {
        if (!s.active_model) return null;
        return {
          ...s.active_model,
          display_status: s.master_paused ? 'paused' : s.active_model.status,
        };
      })
      .filter((m): m is QuickControlModel => !!m);

    return active.sort((a, b) => {
      const pA = STATUS_PRIORITY[a.display_status] ?? 99;
      const pB = STATUS_PRIORITY[b.display_status] ?? 99;
      if (pA !== pB) return pA - pB;
      return a.model_name.localeCompare(b.model_name);
    });
  });

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set('');
    
    // Fetch summaries for the core model task types.
    const tasks: RuntimeModelTaskType[] = ['embedding', 'reranker', 'kg'];
    
    forkJoin(
      tasks.map(t => this.svc.list(t).pipe(
        catchError(() => of(null))
      ))
    ).pipe(
      finalize(() => this.loading.set(false)),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(results => {
      const valid = results.filter((r): r is RuntimeModelsSummary => !!r);
      this.summaries.set(valid);
      if (valid.length === 0) {
        this.error.set($localize`:@@dashboard.quick_controls.error.none:No active model services found.`);
      }
    });
  }

  pause(model: RuntimeModel): void {
    this.runAction(model, 'pause');
  }

  resume(model: RuntimeModel): void {
    this.runAction(model, 'resume');
  }

  promote(model: RuntimeModel): void {
    this.runAction(model, 'promote');
  }

  drain(model: RuntimeModel): void {
    this.runAction(model, 'drain');
  }

  private runAction(model: RuntimeModel, action: RuntimeModelAction): void {
    if (this.busyId()) return;
    
    this.busyId.set(`${model.id}:${action}`);
    this.svc.action(model.id, action).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        const name = model.model_name;
        const msg = $localize`:@@dashboard.quick_controls.snackbar.success:Action "${action}:action:" applied to ${name}:name:.`;
        this.snack.open(msg, $localize`:@@dashboard.quick_controls.snackbar.ok:OK`, { duration: 3000 });
        this.refresh();
      },
      error: () => {
        const name = model.model_name;
        const msg = $localize`:@@dashboard.quick_controls.snackbar.error:Failed to ${action}:action: ${name}:name:.`;
        this.snack.open(msg, $localize`:@@dashboard.quick_controls.snackbar.dismiss:Dismiss`, { duration: 5000 });
      },
      complete: () => {
        this.busyId.set('');
      }
    });
  }

  isBusy(modelId: number, action: string): boolean {
    return this.busyId() === `${modelId}:${action}`;
  }
}
