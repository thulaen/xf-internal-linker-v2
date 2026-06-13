import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CardDirective, CardPadding } from './card.directive';

@Component({
  standalone: true,
  imports: [CardDirective],
  template: `<div appCard [padding]="padding">content</div>`,
})
class HostComponent {
  padding: CardPadding = 'default';
}

describe('CardDirective', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const card = () => fixture.nativeElement.querySelector('div') as HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('paints the flat-white GSC card surface (token-backed)', () => {
    const cls = card().className;
    expect(cls).toContain('bg-surface');
    expect(cls).toContain('border-border');
    expect(cls).toContain('border-solid');
    expect(cls).toContain('border-[0.8px]');
    expect(cls).toContain('rounded-card');
  });

  it('applies the 24px space-lg token padding by default', () => {
    expect(card().className).toContain('p-[var(--space-lg)]');
  });

  it('applies the 16px space-md token padding when dense', () => {
    host.padding = 'dense';
    fixture.detectChanges();
    expect(card().className).toContain('p-[var(--space-md)]');
    expect(card().className).not.toContain('p-[var(--space-lg)]');
  });

  it('applies no built-in padding when padding="none"', () => {
    host.padding = 'none';
    fixture.detectChanges();
    expect(card().className).not.toContain('p-[var(--space-lg)]');
    expect(card().className).not.toContain('p-[var(--space-md)]');
  });

  it('never adds a resting shadow (GSC cards are flat)', () => {
    expect(card().className).not.toContain('shadow');
  });
});
