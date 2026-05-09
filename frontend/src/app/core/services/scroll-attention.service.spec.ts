import { TestBed } from '@angular/core/testing';
import { ScrollAttentionService } from './scroll-attention.service';
import { ScrollHighlightService } from './scroll-highlight.service';

describe('ScrollAttentionService', () => {
  let service: ScrollAttentionService;
  let target: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        ScrollAttentionService,
        { provide: ScrollHighlightService, useValue: {} },
      ],
    });
    service = TestBed.inject(ScrollAttentionService);

    target = document.createElement('div');
    target.id = 'attention-target';
    document.body.appendChild(target);
    spyOn(target, 'scrollIntoView');
    spyOn(target, 'focus');
  });

  afterEach(() => {
    service.dismiss();
    target.remove();
    document.querySelectorAll('.attention-live-region').forEach((el) => el.remove());
  });

  it('returns false when the selector matches nothing', () => {
    expect(service.drawTo('#missing-element')).toBe(false);
  });

  it('returns true and attaches the default pulse class for a valid id', () => {
    expect(service.drawTo('attention-target')).toBe(true);
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });

  it('accepts a leading "#" id', () => {
    service.drawTo('#attention-target');
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });

  it('accepts a CSS class selector', () => {
    target.classList.add('foo');
    service.drawTo('.foo');
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });

  it('accepts an attribute-style selector', () => {
    target.setAttribute('data-x', 'y');
    service.drawTo('[data-x="y"]');
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });

  it('accepts a raw HTMLElement', () => {
    service.drawTo(target);
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });

  it('uses priority-specific pulse class for "low"', () => {
    service.drawTo(target, { priority: 'low' });
    expect(target.classList.contains('attention-pulse-low')).toBe(true);
  });

  it('uses priority-specific pulse class for "urgent"', () => {
    service.drawTo(target, { priority: 'urgent' });
    expect(target.classList.contains('attention-pulse-urgent')).toBe(true);
  });

  it('uses an explicit pulseClass override when provided', () => {
    service.drawTo(target, { pulseClass: 'custom-pulse' });
    expect(target.classList.contains('custom-pulse')).toBe(true);
  });

  it('moves keyboard focus to the target by default', () => {
    service.drawTo(target);
    expect(target.focus).toHaveBeenCalled();
    expect(target.getAttribute('tabindex')).toBe('-1');
  });

  it('preserves a pre-existing tabindex on the target', () => {
    target.setAttribute('tabindex', '0');
    service.drawTo(target);
    expect(target.getAttribute('tabindex')).toBe('0');
  });

  it('does NOT steal focus when the user is typing in an INPUT (priority normal)', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    service.drawTo(target, { priority: 'normal' });
    expect(target.focus).not.toHaveBeenCalled();
    input.remove();
  });

  it('DOES steal focus when priority is urgent, even while typing', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();
    service.drawTo(target, { priority: 'urgent' });
    expect(target.focus).toHaveBeenCalled();
    input.remove();
  });

  it('emits an aria-live announcement when announce text is supplied', (done) => {
    service.drawTo(target, { announce: 'Pipeline failed' });
    setTimeout(() => {
      const region = document.querySelector('.attention-live-region');
      expect(region?.textContent).toBe('Pipeline failed');
      done();
    }, 30);
  });

  it('dismiss() removes the pulse class and stops the ESC listener', () => {
    service.drawTo(target);
    expect(target.classList.contains('attention-pulse')).toBe(true);
    service.dismiss();
    expect(target.classList.contains('attention-pulse')).toBe(false);
  });

  it('a second drawTo() cancels the first pulse before applying its own class', () => {
    service.drawTo(target, { priority: 'low' });
    expect(target.classList.contains('attention-pulse-low')).toBe(true);
    service.drawTo(target, { priority: 'urgent' });
    expect(target.classList.contains('attention-pulse-low')).toBe(false);
    expect(target.classList.contains('attention-pulse-urgent')).toBe(true);
  });

  it('ESC keypress dismisses the active pulse', () => {
    service.drawTo(target);
    expect(target.classList.contains('attention-pulse')).toBe(true);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(target.classList.contains('attention-pulse')).toBe(false);
  });

  it('non-Escape keypresses do NOT dismiss the pulse', () => {
    service.drawTo(target);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(target.classList.contains('attention-pulse')).toBe(true);
  });
});
