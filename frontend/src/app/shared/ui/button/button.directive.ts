import { Directive, HostBinding, Input } from '@angular/core';

export type ButtonVariant = 'primary' | 'outline' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

/**
 * Owned button primitive (CDK + Tailwind stack — Material-free).
 *
 * A directive applied to a native `<button>`/`<a>` so semantics + native
 * behaviour are preserved (the shadcn/spartan approach), with Tailwind classes
 * for the look. Replaces `mat-button` / `mat-stroked-button` / `mat-flat-button`.
 *
 *   <button appBtn>Primary</button>
 *   <a appBtn variant="outline" [routerLink]="...">Outline</a>
 *   <button appBtn variant="ghost" size="sm">Ghost</button>
 *
 * Colours/spacing come from the token-mapped Tailwind theme (bg-primary,
 * text-on-dark, ring-primary, …). Class strings are full literals so Tailwind's
 * scanner emits them.
 */
const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md font-medium no-underline ' +
  'transition-colors cursor-pointer select-none ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-primary ' +
  'disabled:opacity-50 disabled:pointer-events-none';

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-on-dark hover:bg-primary-dark',
  outline: 'border border-primary text-primary bg-surface hover:bg-blue-50',
  ghost: 'text-primary hover:bg-faint',
};

const SIZE: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-9 px-4 text-sm',
  lg: 'h-11 px-6 text-base',
};

@Directive({
  selector: '[appBtn]',
  standalone: true,
})
export class ButtonDirective {
  @Input() variant: ButtonVariant = 'primary';
  @Input() size: ButtonSize = 'md';

  @HostBinding('class')
  get classes(): string {
    return `${BASE} ${VARIANT[this.variant]} ${SIZE[this.size]}`;
  }
}
