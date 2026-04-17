import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

/**
 * Phase MX2 / Gaps 312 + 313 + 308 — "Recommended: X" + "Why change this?"
 * hint shown next to any settings field.
 *
 * Usage:
 *   <app-recommended-hint
 *     [recommended]="'0.2'"
 *     [current]="form.controls.weight.value"
 *     why="Raise to 0.3 if you see under-linking. Lower to 0.1 if you see spam."
 *   />
 *
 * Renders:
 *   • a green-text pill "Recommended: 0.2" — plus a checkmark when
 *     the current value matches the recommended one.
 *   • an info icon with the `why` blurb in a tooltip.
 *   • Gap 308 impact preview is driven by the caller passing
 *     `[impactText]="'Affects: review ranking, link health'"`.
 *
 * Pure presentation — no HTTP, no state. Cheap enough to drop on
 * every field in the settings form without noticeable render cost.
 */
@Component({
  selector: 'app-recommended-hint',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    @if (recommended !== null && recommended !== undefined) {
      <span class="rh-line">
        <span
          class="rh-pill"
          [class.rh-match]="matchesRecommended"
          [matTooltip]="matchesRecommended
            ? 'Your current value matches the recommended default.'
            : 'This is the research-backed default for this field.'"
        >
          @if (matchesRecommended) {
            <mat-icon inline>check_circle</mat-icon>
          } @else {
            <mat-icon inline>auto_awesome</mat-icon>
          }
          Recommended: {{ recommended }}
        </span>
        @if (why) {
          <mat-icon
            class="rh-why"
            [matTooltip]="why"
            matTooltipPosition="above"
            aria-label="Why change this value"
          >help_outline</mat-icon>
        }
        @if (impactText) {
          <span class="rh-impact" [matTooltip]="impactText">
            <mat-icon inline>radar</mat-icon>
            Impacts downstream
          </span>
        }
      </span>
    }
  `,
  styles: [`
    :host { display: inline-flex; }
    .rh-line {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
    }
    .rh-pill {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 10px;
      background: #e6f4ea;
      color: #137333;
      font-weight: 500;
    }
    .rh-match { background: #e8f0fe; color: #1967d2; }
    .rh-why {
      width: 16px;
      height: 16px;
      font-size: 16px;
      color: var(--color-text-secondary, #5f6368);
      cursor: help;
    }
    .rh-impact {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--color-text-secondary, #5f6368);
    }
    .rh-impact mat-icon { width: 14px; height: 14px; font-size: 14px; }
  `],
})
export class RecommendedHintComponent {
  @Input() recommended: string | number | null = null;
  @Input() current: string | number | null = null;
  @Input() why = '';
  @Input() impactText = '';

  get matchesRecommended(): boolean {
    if (this.recommended === null || this.recommended === undefined) return false;
    if (this.current === null || this.current === undefined) return false;
    return String(this.recommended).trim() === String(this.current).trim();
  }
}
