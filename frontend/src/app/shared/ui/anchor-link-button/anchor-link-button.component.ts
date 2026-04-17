import { ChangeDetectionStrategy, Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

/**
 * Phase GK1 / Gap 211 — Bookmarkable in-page anchors.
 *
 * Renders a small "copy link to this section" icon-button that writes
 * `${window.location.origin}${window.location.pathname}#${id}` to the
 * clipboard. Cards / sections just drop one next to their heading:
 *
 *   <h2>
 *     Throughput
 *     <app-anchor-link-button anchorId="throughput" />
 *   </h2>
 */
@Component({
  selector: 'app-anchor-link-button',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatTooltipModule, MatSnackBarModule],
  template: `
    <button
      mat-icon-button
      type="button"
      class="anchor-link-btn"
      [matTooltip]="tooltip()"
      matTooltipPosition="above"
      (click)="copyLink()"
      aria-label="Copy link to this section"
    >
      <mat-icon>link</mat-icon>
    </button>
  `,
  styles: [`
    :host { display: inline-flex; }
    .anchor-link-btn { opacity: 0; transition: opacity 0.2s; }
    :host-context(:hover) .anchor-link-btn,
    .anchor-link-btn:focus-visible {
      opacity: 1;
    }
    :host(.always-visible) .anchor-link-btn { opacity: 1; }
  `],
})
export class AnchorLinkButtonComponent {
  @Input() anchorId = '';

  private snack = inject(MatSnackBar);

  protected tooltip(): string {
    return this.anchorId
      ? `Copy link to "${this.anchorId}"`
      : 'Copy link to this section';
  }

  async copyLink(): Promise<void> {
    if (!this.anchorId) return;
    const url = `${window.location.origin}${window.location.pathname}#${this.anchorId}`;
    try {
      await navigator.clipboard.writeText(url);
      this.snack.open('Link copied — paste to share.', 'OK', { duration: 2500 });
    } catch {
      this.snack.open(
        'Could not copy — long-press your browser address bar and share manually.',
        'OK',
        { duration: 4000 },
      );
    }
  }
}
