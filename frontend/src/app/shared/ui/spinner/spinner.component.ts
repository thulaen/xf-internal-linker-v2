import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

export type SpinnerSize = 'sm' | 'md' | 'lg';

/**
 * Owned spinner primitive (Tailwind, Material-free) — replaces
 * `mat-spinner` / `mat-progress-spinner`. An indeterminate circular loader: a
 * faint track ring plus a spinning arc, both tinted with `currentColor`
 * (primary blue by default). Sizes mirror the Material diameters the
 * component-state rules call for: 18px inline (sm), 24px in-card (md), 48px
 * full-page (lg). Uses Tailwind's built-in `animate-spin` (no custom keyframe).
 */
const SIZE: Record<SpinnerSize, string> = {
  sm: 'h-[18px] w-[18px]', // inline beside a button label
  md: 'h-6 w-6', //          in-card (24px)
  lg: 'h-12 w-12', //        full-page (48px)
};

@Component({
  selector: 'app-spinner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      [class]="classes"
      viewBox="0 0 24 24"
      fill="none"
      role="progressbar"
      [attr.aria-label]="label"
      [attr.aria-valuetext]="label"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      ></circle>
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4z"
      ></path>
    </svg>
  `,
})
export class SpinnerComponent {
  @Input() size: SpinnerSize = 'md';
  @Input() label = 'Loading';

  get classes(): string {
    return `inline-block animate-spin text-primary ${SIZE[this.size]}`;
  }
}
