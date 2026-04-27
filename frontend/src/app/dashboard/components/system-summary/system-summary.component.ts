import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-system-summary',
  standalone: true,
  imports: [CommonModule, RouterModule, MatIconModule, MatTooltipModule],
  templateUrl: './system-summary.component.html',
  styleUrls: ['./system-summary.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemSummaryComponent {
  @Input() health: {
    status: 'healthy' | 'warning' | 'error' | 'down' | 'stale';
    summary: { [key: string]: number };
    total_monitored: number;
  } | null = null;

  getStatusIcon(): string {
    if (!this.health) return 'help_outline';
    switch (this.health.status) {
      case 'healthy': return 'check_circle';
      case 'warning': return 'warning';
      case 'error':   return 'error';
      case 'down':    return 'dangerous';
      case 'stale':   return 'update';
      default:        return 'help_outline';
    }
  }

  getDegradedCount(): number {
    if (!this.health) return 0;
    const s = this.health.summary;
    return (s['warning'] || 0) + (s['error'] || 0) + (s['down'] || 0) + (s['stale'] || 0);
  }
}
