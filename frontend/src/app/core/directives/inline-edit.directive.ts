import {
  Directive,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  Output,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase GK1 / Gap 220 — Inline-edit a table cell by double-click.
 *
 * Wrap any static text span with this directive:
 *   <span [appInlineEdit]="row.anchor"
 *         (editCommit)="save(row, $event)">
 *     {{ row.anchor }}
 *   </span>
 *
 * Double-click swaps the text for an `<input>` focused + selected,
 * Enter commits (emits `editCommit`), Escape cancels (emits
 * `editCancel`). Blur commits by default; pass `[commitOnBlur]="false"`
 * to cancel on blur instead.
 *
 * No MatFormField chrome — this is for quick grid edits, not form
 * fields. Use a real `mat-form-field` for rich editing.
 */
@Directive({
  selector: '[appInlineEdit]',
  standalone: true,
})
export class InlineEditDirective {
  @Input('appInlineEdit') initialValue = '';
  @Input() commitOnBlur = true;
  @Input() inputType: 'text' | 'number' = 'text';

  @Output() editCommit = new EventEmitter<string>();
  @Output() editCancel = new EventEmitter<void>();

  private el = inject(ElementRef<HTMLElement>);
  private renderer = inject(Renderer2);
  private input: HTMLInputElement | null = null;

  @HostListener('dblclick', ['$event'])
  onDblClick(ev: MouseEvent): void {
    ev.preventDefault();
    if (this.input) return; // already editing
    this.openEditor();
  }

  private openEditor(): void {
    const input = this.renderer.createElement('input') as HTMLInputElement;
    input.type = this.inputType;
    input.value = this.initialValue ?? this.el.nativeElement.innerText.trim();
    input.className = 'inline-edit-input';
    input.setAttribute('aria-label', 'Edit value');
    input.style.font = 'inherit';
    input.style.padding = '2px 4px';
    input.style.border = '1px solid var(--color-primary, #1a73e8)';
    input.style.borderRadius = '3px';
    input.style.background = 'var(--color-bg, #ffffff)';
    input.style.minWidth = '120px';

    const host = this.el.nativeElement;
    host.style.display = 'inline-block';
    host.innerHTML = '';
    host.appendChild(input);
    this.input = input;

    input.addEventListener('keydown', this.onKeyDown);
    if (this.commitOnBlur) input.addEventListener('blur', this.commit);
    else input.addEventListener('blur', this.cancel);
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  }

  private onKeyDown = (ev: KeyboardEvent): void => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      this.commit();
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancel();
    }
  };

  private commit = (): void => {
    const value = this.input?.value ?? '';
    this.closeEditor(value);
    this.editCommit.emit(value);
  };

  private cancel = (): void => {
    this.closeEditor(this.initialValue);
    this.editCancel.emit();
  };

  private closeEditor(text: string): void {
    if (!this.input) return;
    this.input.removeEventListener('keydown', this.onKeyDown);
    this.input.removeEventListener('blur', this.commit);
    this.input.removeEventListener('blur', this.cancel);
    this.el.nativeElement.innerHTML = '';
    this.el.nativeElement.appendChild(document.createTextNode(text));
    this.input = null;
  }
}
