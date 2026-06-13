import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ChipComponent, ChipTone } from './chip.component';

@Component({
  standalone: true,
  imports: [ChipComponent],
  template: `
    <app-chip [tone]="tone" [removable]="removable" (removed)="onRemoved()">Tag</app-chip>
  `,
})
class HostComponent {
  tone: ChipTone = 'neutral';
  removable = false;
  removedCount = 0;
  onRemoved(): void {
    this.removedCount++;
  }
}

describe('ChipComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const pill = () => fixture.nativeElement.querySelector('span') as HTMLElement;
  const removeBtn = () =>
    fixture.nativeElement.querySelector('button') as HTMLButtonElement | null;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders a flat pill with the neutral tone by default', () => {
    const cls = pill().className;
    expect(cls).toContain('rounded-pill');
    expect(cls).toContain('bg-faint');
    expect(cls).not.toContain('shadow');
    expect(pill().textContent).toContain('Tag');
  });

  it('uses the tinted primary tone', () => {
    host.tone = 'primary';
    fixture.detectChanges();
    const cls = pill().className;
    expect(cls).toContain('bg-blue-50');
    expect(cls).toContain('text-primary');
  });

  it('hides the remove affordance unless removable', () => {
    expect(removeBtn()).toBeNull();
  });

  it('emits (removed) when the remove affordance is clicked', () => {
    host.removable = true;
    fixture.detectChanges();
    const btn = removeBtn();
    expect(btn).not.toBeNull();
    expect(btn!.getAttribute('aria-label')).toBe('Remove');
    btn!.click();
    expect(host.removedCount).toBe(1);
  });
});
