import { ChangeDetectionStrategy, Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SystemConflict } from '../diagnostics.service';

@Component({
  selector: 'app-conflict-list',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './conflict-list.component.html',
  styleUrls: ['./conflict-list.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConflictListComponent {
  @Input() conflicts: SystemConflict[] = [];
  @Output() resolve = new EventEmitter<number>();

  getSeverityClass(severity: string): string {
    return `severity-${severity}`;
  }

  trackByIndex(index: number): number { return index; }

  getConflictIcon(type: string): string {
    switch (type) {
      case 'duplication': return 'content_copy';
      case 'mismatch': return 'difference';
      case 'placeholder': return 'construction';
      case 'drift': return 'history';
      default: return 'report_problem';
    }
  }
}
