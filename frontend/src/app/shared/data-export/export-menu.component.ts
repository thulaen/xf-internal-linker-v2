import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase E2 / Gap 46 — CSV / JSON export menu.
 *
 * Drop onto any data table:
 *
 *   <app-export-menu
 *     [rows]="items"
 *     filename="suggestions"
 *   />
 *
 * Produces a three-dot menu with "Export as CSV" and "Export as JSON".
 * Generates the file in-memory, triggers a Blob download, cleans up.
 *
 * Column selection:
 *   - If `columns` is provided, only those keys are exported (in order).
 *   - Otherwise the union of all row keys is used (preserves first-seen
 *     order across rows).
 *
 * CSV dialect:
 *   - RFC 4180: `"` escaped by doubling; fields containing `,` `"` CR or LF
 *     are quoted.
 *   - UTF-8 with BOM so Excel opens it as UTF-8 instead of Windows-1252.
 *   - Line terminator = `\r\n` (again, Excel).
 *
 * This component does NOT hit the server — it exports whatever rows you
 * pass in. For very large datasets you want a backend endpoint. For the
 * 99% case (a table the user is already looking at), in-memory is right.
 */
@Component({
  selector: 'app-export-menu',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
  ],
  template: `
    <button
      mat-icon-button
      matTooltip="Export…"
      aria-label="Export data"
      [matMenuTriggerFor]="exportMenu"
      [disabled]="!rows || rows.length === 0"
    >
      <mat-icon>download</mat-icon>
    </button>
    <mat-menu #exportMenu="matMenu" xPosition="before">
      <button mat-menu-item (click)="exportCsv()">
        <mat-icon>table_chart</mat-icon>
        <span>Export as CSV</span>
      </button>
      <button mat-menu-item (click)="exportJson()">
        <mat-icon>code</mat-icon>
        <span>Export as JSON</span>
      </button>
    </mat-menu>
  `,
})
export class ExportMenuComponent {
  /** Rows to export. Each row is a plain object. */
  @Input() rows: readonly Record<string, unknown>[] = [];

  /** Optional explicit column order. When omitted, the union of all row
   *  keys is used (first-seen order across rows). */
  @Input() columns: readonly string[] | null = null;

  /** Base filename (no extension). ".csv" / ".json" appended on export. */
  @Input() filename = 'export';

  exportCsv(): void {
    if (!this.rows || this.rows.length === 0) return;
    const cols = this.resolveColumns();
    const lines: string[] = [];
    lines.push(cols.map(csvCell).join(','));
    for (const row of this.rows) {
      lines.push(cols.map((c) => csvCell(row[c])).join(','));
    }
    // `\ufeff` = UTF-8 BOM, tells Excel to read the file as UTF-8.
    const csv = '\ufeff' + lines.join('\r\n') + '\r\n';
    this.triggerDownload(csv, 'text/csv;charset=utf-8', `${this.filename}.csv`);
  }

  exportJson(): void {
    if (!this.rows || this.rows.length === 0) return;
    const cols = this.columns;
    const payload = cols
      ? this.rows.map((r) => Object.fromEntries(cols.map((c) => [c, r[c]])))
      : this.rows;
    const json = JSON.stringify(payload, null, 2);
    this.triggerDownload(json, 'application/json;charset=utf-8', `${this.filename}.json`);
  }

  private resolveColumns(): string[] {
    if (this.columns && this.columns.length > 0) return [...this.columns];
    // Union of all keys, preserving insertion order across the first
    // appearance in each row.
    const seen = new Set<string>();
    for (const row of this.rows) {
      for (const k of Object.keys(row)) {
        if (!seen.has(k)) seen.add(k);
      }
    }
    return [...seen];
  }

  private triggerDownload(data: string, mime: string, filename: string): void {
    const blob = new Blob([data], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    // Firefox needs the anchor in the DOM to honour the download attr.
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Revoke on the next frame so slow browsers have time to start the
    // download before the blob URL is freed.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

/**
 * RFC 4180-compliant CSV cell formatter.
 *
 * Rules:
 *   - null / undefined → empty string.
 *   - Date → ISO string.
 *   - boolean, number, bigint → their .toString().
 *   - object/array → JSON.stringify.
 *   - After stringifying, if the value contains `"` `,` `\r` or `\n`,
 *     wrap in double quotes and escape any embedded `"` by doubling.
 */
function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  let s: string;
  if (value instanceof Date) {
    s = value.toISOString();
  } else if (typeof value === 'object') {
    try {
      s = JSON.stringify(value);
    } catch {
      s = String(value);
    }
  } else {
    s = String(value);
  }
  if (/[",\r\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}
