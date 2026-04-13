import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { ScrollHighlightService } from '../../core/services/scroll-highlight.service';

export interface DeepLinkTarget {
  route: string;
  fragment?: string;
  targetId?: string;
}

@Injectable({ providedIn: 'root' })
export class NavigationCoordinatorService {
  private router = inject(Router);
  private scrollHighlight = inject(ScrollHighlightService);

  navigateTo(target: DeepLinkTarget): void {
    const extras: Record<string, unknown> = {};
    if (target.fragment) {
      extras['fragment'] = target.fragment;
    }

    this.router.navigate([target.route], extras).then((navigated) => {
      if (!navigated) return;

      // Allow the route component to render before scrolling.
      setTimeout(() => {
        const elementId = target.targetId ?? target.fragment;
        if (elementId) {
          this.scrollHighlight.scrollToAndHighlight(elementId);
        }
      }, 300);
    });
  }
}
