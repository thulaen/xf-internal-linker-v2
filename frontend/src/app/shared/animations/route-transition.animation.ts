import { trigger, transition, style, animate, query } from '@angular/animations';

/**
 * Route transition animation.
 *
 * Phase E1 / Gap 39 — respects prefers-reduced-motion.
 * When the user has `prefers-reduced-motion: reduce` set in their OS, Angular
 * animations still run but we use a duration of 0ms so the element appears
 * instantly (the opacity crossfade vanishes, translateY stays 0).
 *
 * The CSS media query handles this at Angular Animation layer by reading a
 * CSS custom property set in styles.scss. We use a JS-side check for the
 * runtime preference and pass duration 0 when motion is reduced.
 */

function reducedMotion(): boolean {
  return typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

export const routeTransitionAnimation = trigger('routeAnimation', [
  transition('* <=> *', [
    query(':enter', [
      style({ opacity: 0, transform: reducedMotion() ? 'translateY(0)' : 'translateY(8px)' }),
      animate(
        reducedMotion() ? '0ms' : '200ms ease',
        style({ opacity: 1, transform: 'translateY(0)' }),
      ),
    ], { optional: true }),
  ]),
]);
