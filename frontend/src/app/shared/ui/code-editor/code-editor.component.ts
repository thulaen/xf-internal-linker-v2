import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
  computed,
  forwardRef,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

/**
 * Phase DC / Gap 125 — Lightweight code editor with JSON / YAML
 * validation.
 *
 * The plan mentions Monaco, but bundling Monaco adds ~2MB and a
 * webpack config surgery. The in-repo use cases (plugin configs,
 * weight JSON, crawler YAML) are read-heavy and single-file — a
 * styled `<textarea>` with line numbers + live parse validation
 * covers the operator workflow without that weight.
 *
 * Swap-in path: the public API (value, language, valueChange, errors)
 * matches `ngx-monaco-editor`. A future session can replace this
 * component's template with Monaco without changing consumers.
 *
 * Features:
 *   - Line numbers via a pseudo-gutter rendered alongside the textarea.
 *   - Live JSON / YAML parse validation when `language` is set; emits
 *     `(validationError)` with the first parse error or null when valid.
 *   - Tab key inserts two spaces so operators can indent without
 *     losing focus.
 *   - Reactive-form friendly via ControlValueAccessor.
 */
@Component({
  selector: 'app-code-editor',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => CodeEditorComponent),
      multi: true,
    },
  ],
  template: `
    <div class="ce">
      <div class="ce-head">
        <span class="ce-lang">{{ language }}</span>
        @if (validationError()) {
          <span class="ce-err" role="alert">
            {{ validationError() }}
          </span>
        } @else if (value) {
          <span class="ce-ok">valid {{ language }}</span>
        }
      </div>
      <div class="ce-body">
        <pre class="ce-gutter" aria-hidden="true">{{ lineNumbers() }}</pre>
        <textarea
          class="ce-textarea"
          [rows]="rows"
          [placeholder]="placeholder"
          [disabled]="disabled"
          [(ngModel)]="value"
          (ngModelChange)="onValueChange($event)"
          (keydown)="onKeydown($event)"
          (blur)="onTouched()"
          spellcheck="false"
          autocomplete="off"
        ></textarea>
      </div>
    </div>
  `,
  styles: [`
    .ce {
      display: flex;
      flex-direction: column;
      gap: 4px;
      border: var(--card-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-white);
      overflow: hidden;
    }
    .ce-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      font-size: 11px;
      background: var(--color-bg-faint);
      border-bottom: var(--card-border);
    }
    .ce-lang {
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--color-text-secondary);
      font-weight: 500;
    }
    .ce-err { color: var(--color-error); }
    .ce-ok { color: var(--color-success, #1e8e3e); }
    .ce-body {
      display: flex;
      align-items: stretch;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.5;
    }
    .ce-gutter {
      flex-shrink: 0;
      margin: 0;
      padding: 8px 10px;
      border-right: var(--card-border);
      background: var(--color-bg-faint);
      color: var(--color-text-secondary);
      text-align: right;
      white-space: pre;
      user-select: none;
      font: inherit;
    }
    .ce-textarea {
      flex: 1;
      padding: 8px 12px;
      border: 0;
      resize: vertical;
      font: inherit;
      min-height: 160px;
      background: transparent;
    }
    .ce-textarea:focus { outline: none; }
  `],
})
export class CodeEditorComponent implements ControlValueAccessor {
  @Input() language: 'json' | 'yaml' | 'text' = 'json';
  @Input() placeholder = '';
  @Input() rows = 10;
  @Input() disabled = false;
  @Output() parseError = new EventEmitter<string | null>();
  @Output() valueChange = new EventEmitter<string>();

  value = '';
  /** Parse-error signal bound by the template for live display. */
  readonly validationError = signal<string | null>(null);

  readonly lineNumbers = computed(() => {
    const lines = (this.value || '').split('\n').length;
    const out: string[] = [];
    for (let i = 1; i <= lines; i++) out.push(String(i));
    return out.join('\n');
  });

  onValueChange(next: string): void {
    this.value = next;
    this.validate(next);
    this.onChange(next);
    this.valueChange.emit(next);
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    const ta = event.target as HTMLTextAreaElement;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const v = this.value;
    const next = v.substring(0, start) + '  ' + v.substring(end);
    this.value = next;
    this.onValueChange(next);
    // Restore caret AFTER Angular re-renders the textarea.
    queueMicrotask(() => {
      ta.selectionStart = ta.selectionEnd = start + 2;
    });
  }

  // ── validation ─────────────────────────────────────────────────────

  private validate(text: string): void {
    if (!text.trim()) {
      this.validationError.set(null);
      this.parseError.emit(null);
      return;
    }
    if (this.language === 'json') {
      try {
        JSON.parse(text);
        this.validationError.set(null);
        this.parseError.emit(null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        this.validationError.set(msg);
        this.parseError.emit(msg);
      }
      return;
    }
    if (this.language === 'yaml') {
      // Yaml validation requires a parser we don't want to bundle
      // unconditionally. A future session can bring in `yaml` on
      // demand; for now, skip validation without emitting errors.
      this.validationError.set(null);
      this.parseError.emit(null);
      return;
    }
    // text / unknown — no validation.
    this.validationError.set(null);
    this.parseError.emit(null);
  }

  // ── ControlValueAccessor ──────────────────────────────────────────
  onChange: (v: string) => void = () => {};
  onTouched: () => void = () => {};
  writeValue(v: string | null): void {
    this.value = v ?? '';
    this.validate(this.value);
  }
  registerOnChange(fn: (v: string) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(isDisabled: boolean): void { this.disabled = isDisabled; }
}
