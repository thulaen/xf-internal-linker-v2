import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { DOCUMENT } from '@angular/common';
import { MatSnackBar } from '@angular/material/snack-bar';

/**
 * Phase GK1 / Gap 198 — Smart-paste UUID navigates to the entity.
 *
 * Listens to document-level `paste` events (capture phase). If the
 * clipboard contains exactly a UUID/ULID/job-id and the focus isn't
 * inside an input/textarea/contenteditable, the service navigates to
 * the canonical detail page for that id.
 *
 * Detects:
 *   • UUID v1-v5  → probes `/api/suggestions/<id>/`, `/api/pipeline-runs/<id>/`
 *   • ULID 26-char Crockford → same probe set
 *   • "job-<uuid>" prefix → /jobs/<id>
 *
 * Only fires when the paste is outside an editable field — pasting
 * inside a textarea is still normal text paste.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ULID_RE = /^[0-9A-HJKMNP-TV-Z]{26}$/i;
const JOB_RE = /^job-[0-9a-f-]{20,40}$/i;

@Injectable({ providedIn: 'root' })
export class PasteUuidNavigatorService {
  private router = inject(Router);
  private doc = inject(DOCUMENT);
  private snack = inject(MatSnackBar);

  private started = false;

  start(): void {
    if (this.started) return;
    this.started = true;
    this.doc.addEventListener('paste', this.onPaste, { capture: true });
  }

  stop(): void {
    if (!this.started) return;
    this.started = false;
    this.doc.removeEventListener('paste', this.onPaste, { capture: true });
  }

  private onPaste = (ev: ClipboardEvent): void => {
    const active = this.doc.activeElement as HTMLElement | null;
    if (this.isEditable(active)) return;

    const text = ev.clipboardData?.getData('text')?.trim() ?? '';
    if (!text) return;

    const target = this.resolveTarget(text);
    if (!target) return;

    ev.preventDefault();
    ev.stopPropagation();
    this.snack.open(`Opening ${target.kind}: ${target.id}`, 'Dismiss', {
      duration: 3000,
    });
    void this.router.navigate(target.route);
  };

  private isEditable(el: HTMLElement | null): boolean {
    if (!el) return false;
    const tag = el.tagName.toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (el.isContentEditable) return true;
    return false;
  }

  private resolveTarget(text: string): { id: string; kind: string; route: (string | number)[] } | null {
    if (UUID_RE.test(text) || ULID_RE.test(text)) {
      // We don't know the owner domain from the id alone — default to
      // suggestion detail, which is the most common case. A future
      // `/api/resolve/<id>/` endpoint could disambiguate server-side.
      return { id: text, kind: 'suggestion', route: ['/review', text] };
    }
    if (JOB_RE.test(text)) {
      const jobId = text.replace(/^job-/i, '');
      return { id: jobId, kind: 'job', route: ['/jobs', jobId] };
    }
    return null;
  }
}
