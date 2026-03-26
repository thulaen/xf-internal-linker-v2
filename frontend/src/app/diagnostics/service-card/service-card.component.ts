import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ServiceStatus } from '../diagnostics.service';

@Component({
  selector: 'app-service-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './service-card.component.html',
  styleUrls: ['./service-card.component.scss']
})
export class ServiceCardComponent {
  @Input() service!: ServiceStatus;

  getStatusClass(): string {
    return `status-${this.service.state}`;
  }

  getStatusIcon(): string {
    switch (this.service.state) {
      case 'healthy': return 'check_circle';
      case 'degraded': return 'warning';
      case 'failed': return 'error';
      case 'disabled': return 'block';
      case 'not_configured': return 'settings_input_component';
      case 'planned_only': return 'event_note';
      default: return 'help_outline';
    }
  }

  formatState(state: string): string {
    return state.replace(/_/g, ' ');
  }
}
