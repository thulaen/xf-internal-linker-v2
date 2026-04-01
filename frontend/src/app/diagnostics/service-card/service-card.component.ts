import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ServiceStatus } from '../diagnostics.service';

interface MetadataEntry {
  label: string;
  value: string;
}

@Component({
  selector: 'app-service-card',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './service-card.component.html',
  styleUrls: ['./service-card.component.scss']
})
export class ServiceCardComponent implements OnChanges {
  @Input() service!: ServiceStatus;
  metadataEntries: MetadataEntry[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['service']) {
      this.metadataEntries = this.buildMetadataEntries();
    }
  }

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

  private buildMetadataEntries(): MetadataEntry[] {
    const metadata = this.service?.metadata ?? {};

    return Object.entries(metadata)
      .filter(([, value]) => value !== null && value !== undefined && value !== '' && typeof value !== 'object')
      .map(([key, value]) => ({
        label: this.formatState(key),
        value: this.formatMetadataValue(value),
      }));
  }

  private formatMetadataValue(value: unknown): string {
    if (typeof value === 'boolean') {
      return value ? 'Yes' : 'No';
    }

    if (typeof value === 'number' && !Number.isInteger(value)) {
      return value.toFixed(1);
    }

    return String(value);
  }
}
