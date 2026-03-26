import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { DiagnosticsService, DiagnosticsOverview } from '../../../diagnostics/diagnostics.service';

@Component({
  selector: 'app-system-summary',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './system-summary.component.html',
  styleUrls: ['./system-summary.component.scss']
})
export class SystemSummaryComponent implements OnInit {
  private diagnosticsService = inject(DiagnosticsService);
  overview: DiagnosticsOverview | null = null;

  ngOnInit(): void {
    this.diagnosticsService.getOverview().subscribe(data => {
      this.overview = data;
    });
  }
}
