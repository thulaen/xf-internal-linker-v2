import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DividerDirective, DividerOrientation } from './divider.directive';

@Component({
  standalone: true,
  imports: [DividerDirective],
  template: `<hr appDivider [orientation]="orientation" />`,
})
class HostComponent {
  orientation: DividerOrientation = 'horizontal';
}

describe('DividerDirective', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const rule = () => fixture.nativeElement.querySelector('hr') as HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders a horizontal 1px hairline in the border token by default', () => {
    const cls = rule().className;
    expect(cls).toContain('h-px');
    expect(cls).toContain('bg-border');
    expect(cls).toContain('w-full');
    expect(rule().getAttribute('role')).toBe('separator');
    expect(rule().getAttribute('aria-orientation')).toBe('horizontal');
  });

  it('renders a vertical 1px hairline when orientation="vertical"', () => {
    host.orientation = 'vertical';
    fixture.detectChanges();
    const cls = rule().className;
    expect(cls).toContain('w-px');
    expect(cls).toContain('bg-border');
    expect(cls).not.toContain('h-px');
    expect(rule().getAttribute('aria-orientation')).toBe('vertical');
  });
});
