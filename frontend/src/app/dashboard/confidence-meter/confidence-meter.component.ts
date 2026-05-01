import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import {
  ConfidenceContributor,
  ConfidenceSnapshot,
} from '../dashboard.service';

/**
 * Phase 4.3 — Confidence Meter chip.
 *
 * Big single-number "Ready to Rock" score (0-100) with a coloured chip
 * and an expandable drill-down listing each contributor + its fix
 * hint when below max points. Backend payload comes from
 * `apps.core.services.confidence_meter.get_confidence_snapshot`.
 *
 * Renders nothing when `snapshot` is null (backend opted out of the chip
 * because the helper failed). The chip is forward-compatible with the
 * future trend sparkline (sub-gap 3 in plan 4.3).
 */
@Component({
  selector: 'app-confidence-meter',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule,
    MatCardModule,
    MatExpansionModule,
    MatIconModule,
    MatTooltipModule,
    MatProgressBarModule,
  ],
  templateUrl: './confidence-meter.component.html',
  styleUrls: ['./confidence-meter.component.scss'],
})
export class ConfidenceMeterComponent {
  readonly snapshot = input<ConfidenceSnapshot | null | undefined>(null);

  readonly tone = computed<'green' | 'amber' | 'orange' | 'red'>(() => {
    const total = this.snapshot()?.total ?? 0;
    if (total >= 90) return 'green';
    if (total >= 70) return 'amber';
    if (total >= 40) return 'orange';
    return 'red';
  });

  readonly toneIcon = computed<string>(() => {
    switch (this.tone()) {
      case 'green':
        return 'rocket_launch';
      case 'amber':
        return 'check_circle';
      case 'orange':
        return 'warning';
      case 'red':
        return 'error';
    }
  });

  readonly contributorCount = computed<number>(
    () => this.snapshot()?.contributors.length ?? 0,
  );

  readonly weakestContributors = computed<ConfidenceContributor[]>(() => {
    const all = this.snapshot()?.contributors ?? [];
    // Sort by lost-points descending (max_pts - points) so operator
    // sees the highest-impact fix first.
    return [...all]
      .filter((c) => c.points < c.max_pts)
      .sort((a, b) => b.max_pts - b.points - (a.max_pts - a.points));
  });

  trackByName(_index: number, c: ConfidenceContributor): string {
    return c.name;
  }
}
