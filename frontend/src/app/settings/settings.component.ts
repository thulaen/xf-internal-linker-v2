import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import {
  ScopeItem,
  SiloGroup,
  SiloMode,
  SiloSettings,
  SiloSettingsService,
} from './silo-settings.service';

@Component({
  selector: 'app-settings',
  standalone: true,
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
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  private siloSvc = inject(SiloSettingsService);
  private snack = inject(MatSnackBar);

  loading = true;
  savingSettings = false;
  creatingGroup = false;
  settings: SiloSettings = {
    mode: 'disabled',
    same_silo_boost: 0,
    cross_silo_penalty: 0,
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
      label: 'Disabled',
      description: 'Preserve current ranking behaviour with no silo effect.',
    },
    {
      value: 'prefer_same_silo',
      label: 'Prefer same silo',
      description: 'Boost same-silo candidates and penalize cross-silo candidates.',
    },
    {
      value: 'strict_same_silo',
      label: 'Strict same silo',
      description: 'Block cross-silo matches only when both sides have silo assignments.',
    },
  ];

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading = true;
    this.siloSvc.getSettings().subscribe({
      next: (settings) => {
        this.settings = settings;
        this.loadGroupsAndScopes();
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load silo settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  private loadGroupsAndScopes(): void {
    this.siloSvc.listSiloGroups().subscribe({
      next: (groups) => {
        this.siloGroups = groups;
        this.siloSvc.listScopes().subscribe({
          next: (scopes) => {
            this.scopes = scopes;
            this.loading = false;
          },
          error: () => {
            this.loading = false;
            this.snack.open('Failed to load scopes', 'Dismiss', { duration: 4000 });
          },
        });
      },
      error: () => {
        this.loading = false;
        this.snack.open('Failed to load silo groups', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveSettings(): void {
    this.savingSettings = true;
    this.siloSvc.updateSettings(this.settings).subscribe({
      next: (settings) => {
        this.settings = settings;
        this.savingSettings = false;
        this.snack.open('Silo settings saved', undefined, { duration: 2500 });
      },
      error: (error) => {
        this.savingSettings = false;
        this.snack.open(error?.error?.detail || 'Failed to save silo settings', 'Dismiss', { duration: 4000 });
      },
    });
  }

  createGroup(): void {
    if (!this.newGroup.name.trim()) {
      this.snack.open('Group name is required', 'Dismiss', { duration: 3000 });
      return;
    }
    this.creatingGroup = true;
    this.siloSvc.createSiloGroup(this.newGroup).subscribe({
      next: (group) => {
        this.siloGroups = [...this.siloGroups, group].sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
        this.newGroup = { name: '', slug: '', description: '', display_order: 0 };
        this.creatingGroup = false;
        this.snack.open('Silo group created', undefined, { duration: 2500 });
      },
      error: () => {
        this.creatingGroup = false;
        this.snack.open('Failed to create silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  saveGroup(group: SiloGroup): void {
    this.siloSvc.updateSiloGroup(group.id, {
      name: group.name,
      slug: group.slug,
      description: group.description,
      display_order: group.display_order,
    }).subscribe({
      next: (updated) => {
        Object.assign(group, updated);
        this.snack.open('Silo group updated', undefined, { duration: 2500 });
      },
      error: () => {
        this.snack.open('Failed to update silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  deleteGroup(group: SiloGroup): void {
    this.siloSvc.deleteSiloGroup(group.id).subscribe({
      next: () => {
        this.siloGroups = this.siloGroups.filter((item) => item.id !== group.id);
        this.scopes = this.scopes.map((scope) =>
          scope.silo_group === group.id
            ? { ...scope, silo_group: null, silo_group_name: '' }
            : scope
        );
        this.snack.open('Silo group deleted', undefined, { duration: 2500 });
      },
      error: () => {
        this.snack.open('Failed to delete silo group', 'Dismiss', { duration: 4000 });
      },
    });
  }

  updateScope(scope: ScopeItem, siloGroupId: number | null): void {
    this.siloSvc.updateScopeSilo(scope.id, siloGroupId).subscribe({
      next: (updated) => {
        Object.assign(scope, updated);
        this.snack.open('Scope assignment saved', undefined, { duration: 2000 });
      },
      error: () => {
        this.snack.open('Failed to save scope assignment', 'Dismiss', { duration: 4000 });
      },
    });
  }
}
