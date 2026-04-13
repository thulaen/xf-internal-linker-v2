import { Component, Input, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-pulse-indicator',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="pulse-dot" [class.active]="active" [attr.aria-label]="ariaLabel"></span>`,
  styles: [`
    .pulse-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--color-text-muted);
      vertical-align: middle;
    }
    .pulse-dot.active {
      background: var(--color-success);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.5); opacity: 0.3; }
      100% { transform: scale(1); opacity: 1; }
    }
  `],
})
export class PulseIndicatorComponent {
  @Input() active = false;
  @Input() ariaLabel = 'Status indicator';
}
