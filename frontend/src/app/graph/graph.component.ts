/**
 * Link Graph component.
 * D3.js visualization of the internal link graph. Full implementation in Phase 7.
 */

import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-graph',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  templateUrl: './graph.component.html',
  styleUrls: ['./graph.component.scss'],
})
export class GraphComponent {}
