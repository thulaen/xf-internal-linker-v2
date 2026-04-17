import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  EventEmitter,
  Input,
  Output,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatOptionModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';

import { DropzoneComponent } from '../dropzone/dropzone.component';
import { ParseWorkerService } from '../../../core/services/parse-worker.service';

/**
 * Phase DC / Gap 126 — CSV importer with column mapping.
 *
 * Three-stage UX:
 *   1. Drop zone for the CSV.
 *   2. Preview the first 10 rows with header detection.
 *   3. Per-field dropdown mapping each destination field to a CSV
 *      column (or "— skip —").
 *
 * On Import, emits `(importReady)` with the mapped rows as an array
 * of objects keyed by destination field names. Parent posts to
 * whatever backend endpoint accepts the batch.
 *
 * Parsing is offloaded to the Phase F1 web worker so large CSVs
 * don't freeze the main thread.
 *
 * Usage:
 *
 *   <app-csv-importer
 *     [fields]="[{ key: 'url', label: 'Page URL', required: true },
 *                { key: 'title', label: 'Title' }]"
 *     (importReady)="onImport($event)" />
 */

export interface CsvFieldSpec {
  /** Destination key used in the output row. */
  key: string;
  /** User-facing label for the mapping UI. */
  label: string;
  /** When true, a mapping is required before Import is enabled. */
  required?: boolean;
}

@Component({
  selector: 'app-csv-importer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    DropzoneComponent,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatOptionModule,
    MatIconModule,
  ],
  template: `
    <section class="csv">
      @if (rows().length === 0) {
        <app-dropzone
          [accept]="['.csv', 'text/csv']"
          (filesReceived)="onFile($event)"
          (rejected)="onReject($event)"
        >
          Drop a CSV file here, paste one, or click to browse.
          <span class="csv-hint">Header row expected in the first line.</span>
        </app-dropzone>
        @if (parseError()) {
          <p class="csv-error">{{ parseError() }}</p>
        }
      } @else {
        <header class="csv-head">
          <span>
            <strong>{{ rows().length }}</strong>
            rows parsed · {{ headers().length }} columns detected
          </span>
          <button mat-stroked-button type="button" (click)="reset()">
            <mat-icon>restart_alt</mat-icon>
            Choose a different file
          </button>
        </header>

        <table class="csv-preview">
          <thead>
            <tr>
              @for (h of headers(); track h) {
                <th scope="col">{{ h }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (r of previewRows(); track $index) {
              <tr>
                @for (h of headers(); track h) {
                  <td>{{ r[h] }}</td>
                }
              </tr>
            }
          </tbody>
        </table>

        <h3 class="csv-map-title">Map columns to fields</h3>
        <div class="csv-map">
          @for (f of fields; track f.key) {
            <mat-form-field appearance="outline" class="csv-map-field">
              <mat-label>
                {{ f.label }}{{ f.required ? ' *' : '' }}
              </mat-label>
              <mat-select
                [value]="mapping()[f.key] || ''"
                (selectionChange)="setMapping(f.key, $event.value)"
              >
                <mat-option value="">— skip —</mat-option>
                @for (h of headers(); track h) {
                  <mat-option [value]="h">{{ h }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
          }
        </div>

        <footer class="csv-footer">
          <button
            mat-flat-button
            color="primary"
            type="button"
            [disabled]="!canImport()"
            (click)="emitImport()"
          >
            Import {{ rows().length }} row{{ rows().length === 1 ? '' : 's' }}
          </button>
        </footer>
      }
    </section>
  `,
  styles: [`
    .csv { display: flex; flex-direction: column; gap: 16px; }
    .csv-hint { display: block; margin-top: 6px; font-size: 11px; color: var(--color-text-secondary); }
    .csv-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .csv-preview {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      overflow: auto;
      display: block;
    }
    .csv-preview th, .csv-preview td {
      padding: 6px 10px;
      border-bottom: 1px solid var(--color-border-faint);
      text-align: left;
    }
    .csv-preview thead th {
      background: var(--color-bg-faint);
      font-weight: 500;
    }
    .csv-map-title {
      margin: 8px 0 0;
      font-size: 14px;
      font-weight: 500;
    }
    .csv-map {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px;
    }
    .csv-footer {
      display: flex;
      justify-content: flex-end;
    }
    .csv-error {
      margin: 0;
      padding: 8px 12px;
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
      color: var(--color-error-dark, #b3261e);
      border-radius: var(--card-border-radius, 8px);
      font-size: 13px;
    }
  `],
})
export class CsvImporterComponent {
  @Input({ required: true }) fields: readonly CsvFieldSpec[] = [];
  @Output() importReady = new EventEmitter<Array<Record<string, string>>>();
  @Output() rejectedFiles = new EventEmitter<File[]>();

  private readonly parser = inject(ParseWorkerService);
  private readonly destroyRef = inject(DestroyRef);

  readonly rows = signal<readonly Record<string, string>[]>([]);
  readonly headers = signal<readonly string[]>([]);
  readonly mapping = signal<Record<string, string>>({});
  readonly parseError = signal<string | null>(null);

  readonly previewRows = computed(() => this.rows().slice(0, 10));

  readonly canImport = computed(() => {
    if (this.rows().length === 0) return false;
    const m = this.mapping();
    for (const f of this.fields) {
      if (f.required && !m[f.key]) return false;
    }
    return true;
  });

  async onFile(files: File[]): Promise<void> {
    if (files.length === 0) return;
    this.parseError.set(null);
    const file = files[0];
    try {
      const text = await file.text();
      const parsed = (await this.parser.parseCsv(text, true)) as Record<string, string>[];
      if (!Array.isArray(parsed) || parsed.length === 0) {
        this.parseError.set('CSV looks empty or has no header row.');
        return;
      }
      const heads = Object.keys(parsed[0]);
      this.rows.set(parsed);
      this.headers.set(heads);
      // Auto-map fields whose key exactly matches a header.
      const auto: Record<string, string> = {};
      for (const f of this.fields) {
        const hit = heads.find((h) => h.toLowerCase() === f.key.toLowerCase() ||
          h.toLowerCase() === f.label.toLowerCase());
        if (hit) auto[f.key] = hit;
      }
      this.mapping.set(auto);
    } catch (e) {
      this.parseError.set(e instanceof Error ? e.message : 'Could not parse CSV.');
    }
  }

  onReject(files: File[]): void {
    this.parseError.set(
      `${files.length} file${files.length === 1 ? '' : 's'} skipped — CSV files only.`,
    );
    this.rejectedFiles.emit(files);
  }

  setMapping(fieldKey: string, header: string): void {
    this.mapping.set({ ...this.mapping(), [fieldKey]: header });
  }

  emitImport(): void {
    const m = this.mapping();
    const out = this.rows().map((row) => {
      const mapped: Record<string, string> = {};
      for (const [destKey, srcHeader] of Object.entries(m)) {
        if (srcHeader) mapped[destKey] = row[srcHeader] ?? '';
      }
      return mapped;
    });
    this.importReady.emit(out);
  }

  reset(): void {
    this.rows.set([]);
    this.headers.set([]);
    this.mapping.set({});
    this.parseError.set(null);
  }
}
