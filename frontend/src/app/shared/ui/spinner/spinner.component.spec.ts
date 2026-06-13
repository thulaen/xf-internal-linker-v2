import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SpinnerComponent } from './spinner.component';

describe('SpinnerComponent', () => {
  let fixture: ComponentFixture<SpinnerComponent>;
  const svg = () => fixture.nativeElement.querySelector('svg') as SVGElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [SpinnerComponent] }).compileComponents();
    fixture = TestBed.createComponent(SpinnerComponent);
    fixture.detectChanges();
  });

  it('spins and uses the primary token by default', () => {
    expect(svg().getAttribute('class')).toContain('animate-spin');
    expect(svg().getAttribute('class')).toContain('text-primary');
  });

  it('defaults to the 24px (md) size', () => {
    expect(svg().getAttribute('class')).toContain('h-6');
  });

  it('applies the inline (sm, 18px) size', () => {
    fixture.componentInstance.size = 'sm';
    fixture.detectChanges();
    expect(svg().getAttribute('class')).toContain('h-[18px]');
  });

  it('applies the full-page (lg, 48px) size', () => {
    fixture.componentInstance.size = 'lg';
    fixture.detectChanges();
    expect(svg().getAttribute('class')).toContain('h-12');
  });

  it('exposes an accessible progressbar role + label', () => {
    expect(svg().getAttribute('role')).toBe('progressbar');
    expect(svg().getAttribute('aria-label')).toBe('Loading');
  });
});
