import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { GscKpiComponent } from './gsc-kpi.component';

@Component({
  standalone: true,
  imports: [GscKpiComponent],
  template: `
    <app-gsc-kpi
      [label]="label"
      [value]="value"
      [delta]="delta"
      [deltaSuffix]="deltaSuffix"
      [lowerIsBetter]="lowerIsBetter"
    />
  `,
})
class HostComponent {
  label = 'Organic traffic';
  value: string | number = '1.1K';
  delta: number | null = 116;
  deltaSuffix = '%';
  lowerIsBetter = false;
}

describe('GscKpiComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;

  const q = (sel: string) => fixture.nativeElement.querySelector(sel);

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent, NoopAnimationsModule],
    }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the label and value', () => {
    expect(q('.gsc-kpi__label').textContent).toContain('Organic traffic');
    expect(q('.gsc-kpi__value').textContent).toContain('1.1K');
  });

  it('shows a positive (green) delta with an up arrow for a rise', () => {
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-positive');
    expect(delta.textContent).toContain('+116%');
    expect(q('.gsc-kpi__delta mat-icon').textContent.trim()).toBe('arrow_upward');
  });

  it('shows a negative (red) delta with a down arrow for a fall', () => {
    host.delta = -59;
    host.deltaSuffix = '';
    fixture.detectChanges();
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-negative');
    expect(delta.textContent).toContain('-59');
    expect(q('.gsc-kpi__delta mat-icon').textContent.trim()).toBe('arrow_downward');
  });

  it('inverts colour when lowerIsBetter (a fall is good)', () => {
    host.delta = -59;
    host.lowerIsBetter = true;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta').classList).toContain('is-positive');
  });

  it('treats a rise as bad when lowerIsBetter', () => {
    host.delta = 12;
    host.lowerIsBetter = true;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta').classList).toContain('is-negative');
  });

  it('renders a flat (no-change) delta with no arrow when delta is 0', () => {
    host.delta = 0;
    fixture.detectChanges();
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-flat');
    expect(q('.gsc-kpi__delta mat-icon')).toBeNull();
  });

  it('hides the delta entirely when delta is null', () => {
    host.delta = null;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta')).toBeNull();
  });
});
