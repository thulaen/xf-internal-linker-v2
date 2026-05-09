import { TestBed } from '@angular/core/testing';
import { ScrollHighlightService } from './scroll-highlight.service';

/**
 * Unit tests for the ScrollHighlightService. The browser pieces
 * (`scrollIntoView`, `focus`) exist in the jsdom environment but no
 * actual scroll happens — what we verify is the BEHAVIOUR (class
 * applied, focus moved, fade transitions).
 */
describe('ScrollHighlightService', () => {
  let service: ScrollHighlightService;
  let target: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ScrollHighlightService);

    target = document.createElement('div');
    target.id = 'test-target';
    target.style.height = '40px';
    target.style.width = '40px';
    document.body.appendChild(target);
  });

  afterEach(() => {
    service.cancelHighlight();
    target.remove();
  });

  it('applies the highlight class to the target element', () => {
    const result = service.scrollToAndHighlight('#test-target');
    expect(result).toBe(true);
    expect(target.classList.contains('scroll-highlight')).toBe(true);
  });

  it('accepts a selector without the leading "#"', () => {
    service.scrollToAndHighlight('test-target');
    expect(target.classList.contains('scroll-highlight')).toBe(true);
  });

  it('moves keyboard focus to the target (a11y — Gap 7)', () => {
    service.scrollToAndHighlight('#test-target');
    expect(document.activeElement).toBe(target);
  });

  it('sets tabindex="-1" when the target is not natively focusable', () => {
    service.scrollToAndHighlight('#test-target');
    expect(target.getAttribute('tabindex')).toBe('-1');
  });

  it('returns false when the selector does not match anything', () => {
    const result = service.scrollToAndHighlight('#does-not-exist');
    expect(result).toBe(false);
  });

  it('cancelHighlight removes the class from the target', () => {
    service.scrollToAndHighlight('#test-target');
    expect(target.classList.contains('scroll-highlight')).toBe(true);
    service.cancelHighlight();
    expect(target.classList.contains('scroll-highlight')).toBe(false);
  });

  it('does NOT set tabindex on a natively focusable element', () => {
    target.remove();
    const button = document.createElement('button');
    button.id = 'test-target';
    button.textContent = 'Hi';
    document.body.appendChild(button);
    target = button;

    service.scrollToAndHighlight('#test-target');
    expect(button.hasAttribute('tabindex')).toBe(false);
    expect(document.activeElement).toBe(button);
  });
});
