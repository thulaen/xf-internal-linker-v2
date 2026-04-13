import {
  trigger,
  state,
  style,
  transition,
  animate,
  keyframes,
} from '@angular/animations';

export const buttonFeedbackAnimation = trigger('buttonFeedback', [
  state('idle', style({ transform: 'scale(1)' })),
  state('loading', style({ transform: 'scale(0.96)' })),
  state('success', style({ transform: 'scale(1)' })),
  state('error', style({ transform: 'scale(1)' })),

  transition('idle => loading', [
    animate('150ms ease-out', style({ transform: 'scale(0.96)' })),
  ]),

  transition('loading => success', [
    animate('300ms ease-out', keyframes([
      style({ transform: 'scale(1.04)', offset: 0.5 }),
      style({ transform: 'scale(1)', offset: 1.0 }),
    ])),
  ]),

  transition('loading => error', [
    animate('300ms ease-out', keyframes([
      style({ transform: 'translateX(-3px)', offset: 0.2 }),
      style({ transform: 'translateX(3px)', offset: 0.4 }),
      style({ transform: 'translateX(-3px)', offset: 0.6 }),
      style({ transform: 'translateX(0)', offset: 1.0 }),
    ])),
  ]),

  transition('success => idle, error => idle', [
    animate('200ms ease-in'),
  ]),
]);
