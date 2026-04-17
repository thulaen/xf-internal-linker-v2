import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  HostBinding,
  HostListener,
  Input,
  OnInit,
  Output,
  signal, OnDestroy,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

/**
 * Phase DC / Gaps 122 + 123 — Drag-and-drop file dropzone with
 * paste-to-upload support.
 *
 * One component answers both gaps because they share the same
 * receive-and-emit semantics — the source of the file (dropped vs
 * pasted) doesn't matter to the parent, only the File objects.
 *
 * Usage:
 *
 *   <app-dropzone
 *     [accept]="['.csv', '.json']"
 *     [multiple]="false"
 *     (filesReceived)="onFiles($event)"
 *   >
 *     Drop a CSV here or <button>browse</button>.
 *   </app-dropzone>
 *
 * - Listens for dragover/drop on its own element.
 * - Listens for `paste` on `window` while focused (so a clipboard
 *   image or downloaded file can be pasted anywhere on the page).
 * - Validates each file's extension against `accept` (when provided)
 *   and emits only those that match.
 * - Emits `rejected` with the files that failed validation so the
 *   parent can show an error.
 */
@Component({
  selector: 'app-dropzone',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatButtonModule],
  template: `
    <div
      class="dz"
      [class.dz-active]="active()"
      tabindex="0"
      role="button"
      [attr.aria-label]="ariaLabel"
      (click)="openPicker()"
      (keydown.enter)="openPicker()"
      (keydown.space)="openPicker(); $event.preventDefault()"
    >
      <mat-icon class="dz-icon" aria-hidden="true">cloud_upload</mat-icon>
      <div class="dz-body">
        <ng-content />
      </div>
      <input
        type="file"
        class="dz-input"
        [attr.accept]="acceptAttr()"
        [attr.multiple]="multiple || null"
        (change)="onPickerChange($event)"
        #picker
      />
    </div>
  `,
  styles: [`
    .dz {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 24px;
      border: 2px dashed var(--color-border);
      border-radius: var(--card-border-radius, 8px);
      background: var(--color-bg-faint);
      cursor: pointer;
      text-align: center;
      transition: border-color 0.15s ease, background-color 0.15s ease;
    }
    .dz:hover, .dz:focus-visible, .dz.dz-active {
      border-color: var(--color-primary);
      background: var(--color-blue-50, rgba(26, 115, 232, 0.06));
      outline: none;
    }
    .dz-icon {
      font-size: 40px;
      width: 40px;
      height: 40px;
      color: var(--color-primary);
    }
    .dz-body {
      font-size: 13px;
      color: var(--color-text-secondary);
    }
    .dz-input {
      position: absolute;
      width: 0;
      height: 0;
      opacity: 0;
      pointer-events: none;
    }
    @media (prefers-reduced-motion: reduce) {
      .dz { transition: none; }
    }
  `],
})
export class DropzoneComponent implements OnInit, OnDestroy {
  /** Extensions or mime types accepted. Pass `['.csv']` or `['image/*']`. */
  @Input() accept: readonly string[] = [];
  @Input() multiple = false;
  @Input() ariaLabel = 'Drop files here or click to browse';
  /** When true, also listen for window-wide paste events (Gap 123). */
  @Input() pasteToUpload = true;

  @Output() filesReceived = new EventEmitter<File[]>();
  @Output() rejected = new EventEmitter<File[]>();

  readonly active = signal(false);

  @HostBinding('attr.data-dropzone') readonly dataDropzone = 'true';

  ngOnInit(): void {
    if (this.pasteToUpload && typeof window !== 'undefined') {
      window.addEventListener('paste', this.onWindowPaste);
    }
  }

  ngOnDestroy(): void {
    if (typeof window !== 'undefined') {
      window.removeEventListener('paste', this.onWindowPaste);
    }
  }

  openPicker(): void {
    const input = document.querySelector<HTMLInputElement>(
      'input.dz-input:last-of-type',
    );
    input?.click();
  }

  onPickerChange(event: Event): void {
    const input = event.target as HTMLInputElement | null;
    if (!input?.files) return;
    this.accept_(Array.from(input.files));
    input.value = ''; // allow re-picking the same file
  }

  @HostListener('dragover', ['$event'])
  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.active.set(true);
  }

  @HostListener('dragleave')
  onDragLeave(): void {
    this.active.set(false);
  }

  @HostListener('drop', ['$event'])
  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.active.set(false);
    const files = event.dataTransfer?.files;
    if (!files) return;
    this.accept_(Array.from(files));
  }

  acceptAttr(): string | null {
    return this.accept.length > 0 ? this.accept.join(',') : null;
  }

  // ── paste-to-upload ────────────────────────────────────────────────

  private onWindowPaste = (event: ClipboardEvent) => {
    // Ignore pastes that originated inside a text input — those are
    // almost certainly text, not files.
    const target = event.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable)
    ) {
      return;
    }
    const items = event.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const item of Array.from(items)) {
      const f = item.getAsFile();
      if (f) files.push(f);
    }
    if (files.length > 0) {
      event.preventDefault();
      this.accept_(files);
    }
  };

  // ── validation ─────────────────────────────────────────────────────

  private accept_(files: File[]): void {
    if (files.length === 0) return;
    const accepted: File[] = [];
    const rejected: File[] = [];
    for (const f of files) {
      if (this.matchesAccept(f)) accepted.push(f);
      else rejected.push(f);
    }
    if (accepted.length > 0) {
      this.filesReceived.emit(this.multiple ? accepted : [accepted[0]]);
    }
    if (rejected.length > 0) {
      this.rejected.emit(rejected);
    }
  }

  private matchesAccept(f: File): boolean {
    if (this.accept.length === 0) return true;
    for (const rule of this.accept) {
      const r = rule.toLowerCase();
      if (r.startsWith('.')) {
        if (f.name.toLowerCase().endsWith(r)) return true;
      } else if (r.endsWith('/*')) {
        if (f.type.toLowerCase().startsWith(r.slice(0, -1))) return true;
      } else if (f.type.toLowerCase() === r) {
        return true;
      }
    }
    return false;
  }
}
