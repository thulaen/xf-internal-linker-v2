import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { NgClass } from '@angular/common';
import { RouterModule } from '@angular/router';
import { IconComponent } from '../../ui/icon/icon.component';
import { ButtonDirective } from '../../ui/button/button.directive';

type Tone = 'info' | 'warning' | 'success';

const DEFAULT_ICON: Record<Tone, string> = {
  info: 'tips_and_updates',
  warning: 'warning',
  success: 'check_circle',
};

/**
 * Insight / attention banner — Angular CDK + Tailwind stack (Material-free).
 *
 * Composes the owned primitives (app-icon + appBtn) and the token-mapped
 * Tailwind utilities. Polish details aimed at shadcn-grade feel: refined
 * token border, `tracking-tight` heading, secondary detail line, smooth
 * `transition-colors`, and the button's `focus-visible` ring (from appBtn).
 *
 * Tone drives only the icon colour; the card stays flat white (GSC).
 */
@Component({
  selector: 'app-spike-insight-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgClass, RouterModule, IconComponent, ButtonDirective],
  template: `
    <div
      class="flex items-center gap-4 rounded-card border border-border bg-surface p-6 transition-colors"
    >
      <app-icon
        [name]="resolvedIcon"
        class="shrink-0 text-[24px]"
        [ngClass]="iconColorClass"
      />
      <div class="min-w-0 flex-1">
        <p class="m-0 text-base font-medium tracking-tight text-text-primary">{{ headline }}</p>
        @if (detail) {
          <p class="m-0 mt-1 text-sm leading-snug text-text-secondary">{{ detail }}</p>
        }
      </div>
      @if (actionLink && actionLabel) {
        <a class="shrink-0" appBtn variant="outline" [routerLink]="actionLink">{{ actionLabel }}</a>
      }
    </div>
  `,
})
export class SpikeInsightCardComponent {
  @Input() tone: Tone = 'info';
  @Input({ required: true }) headline = '';
  @Input() detail = '';
  @Input() actionLabel: string | null = null;
  @Input() actionLink: string | null = null;
  @Input() icon = '';

  get resolvedIcon(): string {
    return this.icon || DEFAULT_ICON[this.tone];
  }

  /** Full literal classes so Tailwind's scanner emits them. */
  get iconColorClass(): string {
    switch (this.tone) {
      case 'warning':
        return 'text-warning-dark';
      case 'success':
        return 'text-success-dark';
      default:
        return 'text-primary';
    }
  }
}
