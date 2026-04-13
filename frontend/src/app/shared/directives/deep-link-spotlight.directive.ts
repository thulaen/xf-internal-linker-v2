import { Directive, ElementRef, Input, OnInit, OnDestroy, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Subscription } from 'rxjs';

@Directive({
  selector: '[appDeepLinkSpotlight]',
  standalone: true,
})
export class DeepLinkSpotlightDirective implements OnInit, OnDestroy {
  @Input('appDeepLinkSpotlight') spotlightId = '';

  private el = inject(ElementRef);
  private route = inject(ActivatedRoute);
  private sub?: Subscription;

  ngOnInit(): void {
    this.sub = this.route.fragment.subscribe((fragment) => {
      if (fragment && fragment === this.spotlightId) {
        this.spotlight();
      }
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  private spotlight(): void {
    const el = this.el.nativeElement as HTMLElement;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    el.classList.add('deep-link-spotlight');
    setTimeout(() => el.classList.remove('deep-link-spotlight'), 2000);
  }
}
