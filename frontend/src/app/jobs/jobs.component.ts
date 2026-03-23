/**
 * Jobs component.
 * Background Celery job queue with real-time WebSocket progress. Full implementation in Phase 4.
 */

import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-jobs',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  templateUrl: './jobs.component.html',
  styleUrls: ['./jobs.component.scss'],
})
export class JobsComponent {}
