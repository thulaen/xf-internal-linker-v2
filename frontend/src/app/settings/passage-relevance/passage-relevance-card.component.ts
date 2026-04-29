import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, takeUntil, finalize } from 'rxjs';
import { SiloSettingsService, PassageRelevanceSettings } from '../silo-settings.service';
import { MatSnackBar } from '@angular/material/snack-bar';

@Component({
  selector: 'app-passage-relevance-card',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatInputModule,
    MatFormFieldModule,
    MatSlideToggleModule,
    MatTooltipModule,
  ],
  templateUrl: './passage-relevance-card.component.html',
  styleUrls: ['./passage-relevance-card.component.scss']
})
export class PassageRelevanceCardComponent implements OnInit, OnDestroy {
  settings: PassageRelevanceSettings | null = null;
  loading = true;
  saving = false;
  private destroy$ = new Subject<void>();

  constructor(
    private settingsService: SiloSettingsService,
    private snackBar: MatSnackBar,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadSettings();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  loadSettings(): void {
    this.loading = true;
    this.settingsService.getPassageRelevanceSettings()
      .pipe(
        takeUntil(this.destroy$),
        finalize(() => {
          this.loading = false;
          this.cdr.detectChanges();
        })
      )
      .subscribe({
        next: (data) => this.settings = data,
        error: () => this.snackBar.open('Failed to load settings', 'Close', { duration: 3000 })
      });
  }

  saveSettings(): void {
    if (!this.settings) return;
    this.saving = true;
    this.settingsService.updatePassageRelevanceSettings(this.settings)
      .pipe(
        takeUntil(this.destroy$),
        finalize(() => {
          this.saving = false;
          this.cdr.detectChanges();
        })
      )
      .subscribe({
        next: (data) => {
          this.settings = data;
          this.snackBar.open('Settings saved', 'Close', { duration: 2000 });
        },
        error: () => this.snackBar.open('Failed to save settings', 'Close', { duration: 3000 })
      });
  }
}
