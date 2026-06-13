import { Component, ChangeDetectionStrategy } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ButtonDirective, ButtonSize, ButtonVariant } from './button.directive';

@Component({
  standalone: true,
  imports: [ButtonDirective],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `<button appBtn [variant]="variant" [size]="size">Go</button>`,
})
class HostComponent {
  variant: ButtonVariant = 'primary';
  size: ButtonSize = 'md';
}

describe('ButtonDirective', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const btn = () => fixture.nativeElement.querySelector('button') as HTMLButtonElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('applies the shared base classes', () => {
    expect(btn().className).toContain('inline-flex');
    expect(btn().className).toContain('rounded-md');
    expect(btn().className).toContain('focus-visible:ring-primary');
  });

  it('applies primary variant by default', () => {
    expect(btn().className).toContain('bg-primary');
    expect(btn().className).toContain('text-on-dark');
  });

  it('applies outline variant (bordered, no solid fill)', () => {
    host.variant = 'outline';
    fixture.detectChanges();
    expect(btn().className).toContain('border-primary');
    expect(btn().className).not.toContain('bg-primary');
  });

  it('applies ghost variant', () => {
    host.variant = 'ghost';
    fixture.detectChanges();
    expect(btn().className).toContain('hover:bg-faint');
    expect(btn().className).not.toContain('border-primary');
  });

  it('applies the size classes', () => {
    expect(btn().className).toContain('h-9');
    host.size = 'sm';
    fixture.detectChanges();
    expect(btn().className).toContain('h-8');
  });
});
