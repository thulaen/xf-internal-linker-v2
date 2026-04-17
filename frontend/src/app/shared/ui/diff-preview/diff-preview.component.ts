import {
  ChangeDetectionStrategy,
  Component,
  Input,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase DC / Gap 117 — Old → new diff preview.
 *
 * Drop inside any "Are you sure?" dialog before a destructive save:
 *
 *   <app-diff-preview
 *     [oldValue]="currentSettings"
 *     [newValue]="draftSettings"
 *     [labels]="fieldLabels" />
 *
 * Shows a side-by-side table of the fields whose values changed, with
 * removed values on the left (red strikethrough) and incoming values
 * on the right (green). Fields that didn't change are hidden so the
 * reviewer only looks at what actually moves.
 *
 * Why not a text-line diff library: these inputs are typically
 * structured settings objects (flat dicts, small lists). Field-level
 * comparison is both simpler and more actionable than a char diff.
 *
 * Nested objects are rendered via JSON.stringify so the reviewer can
 * at least spot "the whole thing changed." A future session can swap
 * in a recursive tree diff if that signal isn't enough.
 */
@Component({
  selector: 'app-diff-preview',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule],
  template: `
    <section class="dp">
      <header class="dp-head">
        <mat-icon class="dp-icon" aria-hidden="true">compare_arrows</mat-icon>
        <span class="dp-title">
          {{ changes().length }} change{{ changes().length === 1 ? '' : 's' }}
        </span>
      </header>
      @if (changes().length === 0) {
        <p class="dp-empty">No changes — nothing to save.</p>
      } @else {
        <table class="dp-table">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
            </tr>
          </thead>
          <tbody>
            @for (c of changes(); track c.key) {
              <tr>
                <th scope="row" class="dp-field">{{ labelFor(c.key) }}</th>
                <td class="dp-old">
                  <span class="dp-old-text">{{ formatValue(c.oldValue) }}</span>
                </td>
                <td class="dp-new">
                  <span class="dp-new-text">{{ formatValue(c.newValue) }}</span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      }
    </section>
  `,
  styles: [`
    .dp {
      padding: 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
    }
    .dp-head {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
    }
    .dp-icon { color: var(--color-primary); }
    .dp-title {
      font-weight: 500;
      font-size: 13px;
      color: var(--color-text-primary);
    }
    .dp-empty {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-secondary);
      font-style: italic;
    }
    .dp-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .dp-table th,
    .dp-table td {
      padding: 6px 8px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid var(--color-border-faint);
    }
    .dp-table thead th {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
      font-weight: 500;
    }
    .dp-field {
      white-space: nowrap;
      color: var(--color-text-primary);
    }
    .dp-old-text {
      text-decoration: line-through;
      color: var(--color-error-dark, #b3261e);
      background: var(--color-error-50, rgba(217, 48, 37, 0.06));
      padding: 1px 4px;
      border-radius: 3px;
    }
    .dp-new-text {
      color: var(--color-success-dark, #137333);
      background: var(--color-success-light, rgba(30, 142, 62, 0.08));
      padding: 1px 4px;
      border-radius: 3px;
    }
  `],
})
export class DiffPreviewComponent {
  @Input() set oldValue(v: Record<string, unknown> | null | undefined) {
    this._old.set(v ?? {});
  }
  @Input() set newValue(v: Record<string, unknown> | null | undefined) {
    this._new.set(v ?? {});
  }
  /** Optional friendly labels keyed by field name. */
  @Input() labels: Readonly<Record<string, string>> = {};

  private readonly _old = signal<Record<string, unknown>>({});
  private readonly _new = signal<Record<string, unknown>>({});

  readonly changes = computed(() => {
    const oldObj = this._old();
    const newObj = this._new();
    const keys = new Set<string>([...Object.keys(oldObj), ...Object.keys(newObj)]);
    const out: { key: string; oldValue: unknown; newValue: unknown }[] = [];
    for (const k of keys) {
      const a = oldObj[k];
      const b = newObj[k];
      if (!this.equal(a, b)) {
        out.push({ key: k, oldValue: a, newValue: b });
      }
    }
    out.sort((x, y) => x.key.localeCompare(y.key));
    return out;
  });

  labelFor(key: string): string {
    return this.labels[key] ?? this.humanise(key);
  }

  formatValue(v: unknown): string {
    if (v === undefined) return '—';
    if (v === null) return 'null';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }

  private equal(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (a === null || b === null) return false;
    if (typeof a !== typeof b) return false;
    try {
      return JSON.stringify(a) === JSON.stringify(b);
    } catch {
      return false;
    }
  }

  private humanise(name: string): string {
    return name
      .replace(/([A-Z])/g, ' $1')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/^./, (c) => c.toUpperCase());
  }
}
