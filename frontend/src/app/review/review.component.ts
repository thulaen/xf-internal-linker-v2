/**
 * Review Suggestions component.
 * Review, approve, or reject link suggestions before they are applied.
 */

import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-review',
  standalone: true,
  imports: [MatCardModule, MatIconModule],
  templateUrl: './review.component.html',
  styleUrls: ['./review.component.scss'],
})
export class ReviewComponent {}
