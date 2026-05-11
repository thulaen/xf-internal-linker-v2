/**
 * SiloArchitectureTabComponent — Settings tab 2 (Silo Architecture).
 *
 * Extracted from the legacy 4,672-line `SettingsComponent` (AutoIssue #30,
 * slice 2 of 5 of the prevention-cleanup tabs split). Mechanical move;
 * behaviour identical.
 *
 * The silo data is also surfaced by `<app-settings-overview>` (group + scope
 * counts) and bundled in the parent's "Save all" forkJoin (silo mode + boost
 * + penalty), so the parent component continues to load and persist its own
 * copies of `settings`, `siloGroups`, `scopes`, and `assignedScopeCount`.
 * This child duplicates that state internally for the tab UI, owns its own
 * load + save flow, and emits `dirtyChanged` so the parent's
 * `HasUnsavedChanges` guard still fires when the user touches a silo
 * preference.
 */
import { ChangeDetectionStrategy, Component, DestroyRef, EventEmitter, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import {
  ScopeItem,
  SiloGroup,
  SiloMode,
  SiloSettings,
  SiloSettingsService,
} from '../silo-settings.service';

@Component({
  selector: 'app-silo-architecture-tab',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
  ],
  templateUrl: './silo-architecture-tab.component.html',
  styleUrls: ['./silo-architecture-tab.component.scss'],
})
export class SiloArchitectureTabComponent implements OnInit {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);
  private destroyRef = inject(DestroyRef);

  /**
   * Fires `true` whenever the user touches any silo preference, `false`
   * after a successful save. Parent component (`SettingsComponent`)
   * listens so the existing isDirty / unsaved-changes-guard signal
   * continues to work.
   */
  @Output() dirtyChanged = new EventEmitter<boolean>();

  readonly savingSilo = signal(false);
  readonly creatingGroup = signal(false);

  /**
   * Defaults match the original parent-component shape exactly so the
   * dropdown is not blank during the initial render before
   * `loadSettings()` returns. Same starting values as the parent
   * (mode = prefer_same_silo, boost = 0.10, penalty = 0.10) per the
   * March-2026 research-tuned defaults.
   */
  settings: SiloSettings = {
    mode: 'prefer_same_silo',
    same_silo_boost: 0.10,
    cross_silo_penalty: 0.10,
  };

  siloGroups: SiloGroup[] = [];
  scopes: ScopeItem[] = [];

  newGroup: Pick<SiloGroup, 'name' | 'slug' | 'description' | 'display_order'> = {
    name: '',
    slug: '',
    description: '',
    display_order: 0,
  };

  modeOptions: Array<{ value: SiloMode; label: string; description: string }> = [
    {
      value: 'disabled',
      label: $localize`:@@settings.siloArchitecture.modes.disabled:Disabled`,
      description: $localize`:@@settings.siloArchitecture.modes.disabledDesc:Preserve current ranking behaviour with no silo effect.`,
    },
    {
      value: 'prefer_same_silo',
      label: $localize`:@@settings.siloArchitecture.modes.preferSame:Prefer same silo`,
      description: $localize`:@@settings.siloArchitecture.modes.preferSameDesc:Boost same-silo candidates and penalize cross-silo candidates.`,
    },
    {
      value: 'strict_same_silo',
      label: $localize`:@@settings.siloArchitecture.modes.strictSame:Strict same silo`,
      description: $localize`:@@settings.siloArchitecture.modes.strictSameDesc:Block cross-silo matches only when both sides have silo assignments.`,
    },
  ];

  ngOnInit(): void {
    this.siloSvc.getSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          this.settings = { ...this.settings, ...data };
        },
        error: () => {
          this.snack.open($localize`:@@settings.siloArchitecture.errors.loadSettingsFailed:Failed to load silo settings`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
    this.loadGroupsAndScopes();
  }

  /** Bound to every form-field `(ngModelChange)` so dirty signals propagate. */
  markDirty(): void {
    this.dirtyChanged.emit(true);
  }

  get assignedScopeCount(): number {
    return this.scopes.filter((scope) => scope.silo_group !== null).length;
  }

  private loadGroupsAndScopes(): void {
    this.siloSvc.listSiloGroups()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (groups) => {
          this.siloGroups = groups;
          this.siloSvc.listScopes()
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: (scopes) => {
                this.scopes = scopes;
              },
              error: () => {
                this.snack.open($localize`:@@settings.siloArchitecture.errors.loadScopesFailed:Failed to load scopes`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
              },
            });
        },
        error: () => {
          this.snack.open($localize`:@@settings.siloArchitecture.errors.loadGroupsFailed:Failed to load silo groups`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
  }

  saveSettings(): void {
    this.savingSilo.set(true);
    this.siloSvc.updateSettings(this.settings)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (settings) => {
          this.settings = { ...this.settings, ...settings };
          this.savingSilo.set(false);
          this.dirtyChanged.emit(false);
          this.snack.open($localize`:@@settings.siloArchitecture.success.saved:Silo settings saved`, undefined, { duration: 2500 });
        },
        error: (error) => {
          this.savingSilo.set(false);
          this.snack.open(error?.error?.detail || $localize`:@@settings.siloArchitecture.errors.saveFailed:Failed to save silo settings`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
  }

  createGroup(): void {
    if (!this.newGroup.name.trim()) {
      this.snack.open($localize`:@@settings.siloArchitecture.errors.nameRequired:Group name is required`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 3000 });
      return;
    }
    this.creatingGroup.set(true);
    this.siloSvc.createSiloGroup(this.newGroup)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (group) => {
          this.siloGroups = [...this.siloGroups, group].sort(
            (a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name)
          );
          this.newGroup = { name: '', slug: '', description: '', display_order: 0 };
          this.creatingGroup.set(false);
          this.snack.open($localize`:@@settings.siloArchitecture.success.groupCreated:Silo group created`, undefined, { duration: 2500 });
        },
        error: () => {
          this.creatingGroup.set(false);
          this.snack.open($localize`:@@settings.siloArchitecture.errors.groupCreateFailed:Failed to create silo group`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
  }

  saveGroup(group: SiloGroup): void {
    this.siloSvc.updateSiloGroup(group.id, {
      name: group.name,
      slug: group.slug,
      description: group.description,
      display_order: group.display_order,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (updated) => {
        Object.assign(group, updated);
        this.snack.open($localize`:@@settings.siloArchitecture.success.groupUpdated:Silo group updated`, undefined, { duration: 2500 });
      },
      error: () => {
        this.snack.open($localize`:@@settings.siloArchitecture.errors.groupUpdateFailed:Failed to update silo group`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
      },
    });
  }

  deleteGroup(group: SiloGroup): void {
    this.siloSvc.deleteSiloGroup(group.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.siloGroups = this.siloGroups.filter((item) => item.id !== group.id);
          this.scopes = this.scopes.map((scope) =>
            scope.silo_group === group.id
              ? { ...scope, silo_group: null, silo_group_name: '' }
              : scope
          );
          this.snack.open($localize`:@@settings.siloArchitecture.success.groupDeleted:Silo group deleted`, undefined, { duration: 2500 });
        },
        error: () => {
          this.snack.open($localize`:@@settings.siloArchitecture.errors.groupDeleteFailed:Failed to delete silo group`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
  }

  updateScope(scope: ScopeItem, siloGroupId: number | null): void {
    this.siloSvc.updateScopeSilo(scope.id, siloGroupId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          Object.assign(scope, updated);
          this.snack.open($localize`:@@settings.siloArchitecture.success.scopeSaved:Scope assignment saved`, undefined, { duration: 2000 });
        },
        error: () => {
          this.snack.open($localize`:@@settings.siloArchitecture.errors.scopeSaveFailed:Failed to save scope assignment`, $localize`:@@settings.actions.dismiss:Dismiss`, { duration: 4000 });
        },
      });
  }
}
