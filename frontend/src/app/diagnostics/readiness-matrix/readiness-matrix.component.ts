import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FeatureReadiness } from '../diagnostics.service';

@Component({
  selector: 'app-readiness-matrix',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './readiness-matrix.component.html',
  styleUrls: ['./readiness-matrix.component.scss']
})
export class ReadinessMatrixComponent {
  @Input() features: FeatureReadiness[] = [];

  getStatusClass(status: string): string {
    return `status-${status}`;
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'verified': return 'verified';
      case 'implemented': return 'check_circle';
      case 'implementing': return 'pending';
      case 'planned_only': return 'schedule';
      case 'failed': return 'error';
      default: return 'help';
    }
  }

  getStatusLabel(status: string): string {
    return status.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
}
