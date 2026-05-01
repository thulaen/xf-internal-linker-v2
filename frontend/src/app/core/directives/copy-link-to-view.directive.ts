import {
  Directive,
  HostListener,
  Input,
  inject,
} from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

/**
 * Phase 0.15 — "Copy link to this view" directive.
 *
 * Drop on any element (typically a mat-icon-button in a page header) to
 * copy the current `window.location.href` to the operator's clipboard
 * with a confirmation snack-bar. Optional `[copyLinkLabel]` overrides
 * the snack-bar message.
 *
 * Usage:
 *   <button mat-icon-button appCopyLinkToView matTooltip="Copy link to this view">
 *     <mat-icon>link</mat-icon>
 *   </button>
 *
 * Why a directive (not a service): every page header that wants this
 * feature gets a one-line attribute add. No imports, no plumbing, no
 * per-component clipboard logic to maintain. The Group X Deep Linking
 * Catalog (still pending) will read the same `window.location.href`
 * format, so this directive is forward-compatible with the catalog
 * without needing to retrofit each page later.
 *
 * Resilience: clipboard.writeText() can reject on insecure contexts
 * (non-HTTPS) or older browsers. Caught and surfaced as a "Couldn't
 * copy" snack instead of an unhandled promise rejection.
 */
@Directive({
  selector: '[appCopyLinkToView]',
  standalone: true,
})
export class CopyLinkToViewDirective {
  /** Optional override for the success snack-bar message. */
  @Input() copyLinkLabel = 'Link to this view copied to clipboard';

  /** Optional override for the failure snack-bar message. */
  @Input() copyLinkErrorLabel = "Couldn't copy link — your browser blocked clipboard access";

  private readonly snack = inject(MatSnackBar);

  @HostListener('click')
  async onClick(): Promise<void> {
    const url = typeof window !== 'undefined' ? window.location.href : '';
    if (!url) {
      this.snack.open(this.copyLinkErrorLabel, 'Dismiss', { duration: 3500 });
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      this.snack.open(this.copyLinkLabel, 'Dismiss', { duration: 2500 });
    } catch {
      this.snack.open(this.copyLinkErrorLabel, 'Dismiss', { duration: 3500 });
    }
  }
}
