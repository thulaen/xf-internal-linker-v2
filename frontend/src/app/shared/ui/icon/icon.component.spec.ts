import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { IconComponent } from './icon.component';

@Component({
  standalone: true,
  imports: [IconComponent],
  template: `<app-icon [name]="name" />`,
})
class HostComponent {
  name = 'warning';
}

describe('IconComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the material-icons ligature for the given name', () => {
    const span = fixture.nativeElement.querySelector('span.material-icons');
    expect(span).toBeTruthy();
    expect(span.textContent.trim()).toBe('warning');
  });

  it('marks the icon decorative (aria-hidden) by default', () => {
    const span = fixture.nativeElement.querySelector('span.material-icons');
    expect(span.getAttribute('aria-hidden')).toBe('true');
  });

  it('updates when the name changes', () => {
    host.name = 'check_circle';
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('span.material-icons').textContent.trim()).toBe(
      'check_circle',
    );
  });
});
