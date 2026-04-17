import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
  forwardRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { renderMarkdown } from './markdown-render';

/**
 * Phase DC / Gap 124 — Markdown editor + live preview.
 *
 * Three-tab affordance (Edit / Preview / Split) around a textarea.
 * Implements ControlValueAccessor so the consumer can use it inside
 * a reactive form the same as `<input matInput>`:
 *
 *   <mat-form-field>
 *     <mat-label>Runbook description</mat-label>
 *     <app-markdown-editor formControlName="description" />
 *   </mat-form-field>
 *
 * Uses the in-house `markdown-render.ts` sanitiser — only a
 * whitelisted subset of Markdown produces HTML, so paste-attacks
 * can't smuggle `<script>` through.
 */
@Component({
  selector: 'app-markdown-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => MarkdownEditorComponent),
      multi: true,
    },
  ],
  template: `
    <div class="me">
      <mat-button-toggle-group
        [(value)]="mode"
        class="me-tabs"
        aria-label="Editor mode"
      >
        <mat-button-toggle value="edit">Write</mat-button-toggle>
        <mat-button-toggle value="preview">Preview</mat-button-toggle>
        <mat-button-toggle value="split">Split</mat-button-toggle>
      </mat-button-toggle-group>

      <div class="me-body" [class.me-split]="mode === 'split'">
        @if (mode === 'edit' || mode === 'split') {
          <textarea
            class="me-textarea"
            [rows]="rows"
            [placeholder]="placeholder"
            [disabled]="disabled"
            [(ngModel)]="value"
            (ngModelChange)="onChange(value)"
            (blur)="onTouched()"
            spellcheck="true"
            autocomplete="off"
          ></textarea>
        }
        @if (mode === 'preview' || mode === 'split') {
          <div
            class="me-preview"
            [innerHTML]="renderedValue()"
            aria-live="polite"
          ></div>
        }
      </div>
    </div>
  `,
  styles: [`
    .me {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .me-tabs {
      align-self: flex-start;
    }
    .me-body {
      display: block;
      width: 100%;
    }
    .me-body.me-split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .me-textarea {
      width: 100%;
      min-height: 150px;
      padding: 8px 12px;
      font: inherit;
      font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      resize: vertical;
    }
    .me-textarea:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .me-preview {
      padding: 12px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      font-size: 14px;
      line-height: 1.6;
      overflow-x: auto;
    }
    .me-preview h3, .me-preview h4, .me-preview h5 {
      margin: 8px 0 4px;
      color: var(--color-text-primary);
    }
    .me-preview p { margin: 0 0 8px; }
    .me-preview ul, .me-preview ol { margin: 0 0 8px 20px; }
    .me-preview blockquote {
      margin: 0 0 8px;
      padding: 6px 12px;
      border-left: 3px solid var(--color-primary);
      background: var(--color-bg-white);
      color: var(--color-text-secondary);
    }
    .me-preview code {
      font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
      font-size: 13px;
      padding: 1px 4px;
      background: var(--color-bg-white);
      border-radius: 3px;
    }
    .me-preview pre {
      margin: 0 0 8px;
      padding: 10px;
      background: var(--color-bg-white);
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      overflow-x: auto;
    }
    .me-preview a { color: var(--color-primary); }
  `],
})
export class MarkdownEditorComponent implements ControlValueAccessor {
  @Input() placeholder = 'Write markdown here…';
  @Input() rows = 8;
  @Input() disabled = false;

  @Output() readonly valueChange = new EventEmitter<string>();

  mode: 'edit' | 'preview' | 'split' = 'edit';
  value = '';

  onChange: (v: string) => void = () => {};
  onTouched: () => void = () => {};

  renderedValue(): string {
    return renderMarkdown(this.value);
  }

  // ── ControlValueAccessor ──────────────────────────────────────────
  writeValue(v: string | null): void {
    this.value = v ?? '';
  }
  registerOnChange(fn: (v: string) => void): void {
    this.onChange = (v) => {
      fn(v);
      this.valueChange.emit(v);
    };
  }
  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }
  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
  }
}
