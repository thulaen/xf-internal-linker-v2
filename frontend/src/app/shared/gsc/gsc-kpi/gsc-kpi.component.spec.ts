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

  it('Given a label and value, When the KPI component renders, Then both are displayed', () => {
    expect(q('.gsc-kpi__label').textContent).toContain('Organic traffic');
    expect(q('.gsc-kpi__value').textContent).toContain('1.1K');
  });

  it('Given a positive delta, When the component renders, Then it displays a green tone and an up arrow', () => {
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-positive');
    expect(delta.textContent).toContain('+116%');
    expect(q('.gsc-kpi__delta mat-icon').textContent.trim()).toBe('arrow_upward');
  });

  it('Given a negative delta, When the component renders, Then it displays a red tone and a down arrow', () => {
    host.delta = -59;
    host.deltaSuffix = '';
    fixture.detectChanges();
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-negative');
    expect(delta.textContent).toContain('-59');
    expect(q('.gsc-kpi__delta mat-icon').textContent.trim()).toBe('arrow_downward');
  });

  it('Given a negative delta and lowerIsBetter is true, When it renders, Then the delta shows as positive (green)', () => {
    host.delta = -59;
    host.lowerIsBetter = true;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta').classList).toContain('is-positive');
  });

  it('Given a positive delta and lowerIsBetter is true, When it renders, Then the delta shows as negative (red)', () => {
    host.delta = 12;
    host.lowerIsBetter = true;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta').classList).toContain('is-negative');
  });

  it('Given a delta of 0, When it renders, Then it shows a flat tone without an arrow', () => {
    host.delta = 0;
    fixture.detectChanges();
    const delta = q('.gsc-kpi__delta');
    expect(delta.classList).toContain('is-flat');
    expect(q('.gsc-kpi__delta mat-icon')).toBeNull();
  });

  it('Given a null delta, When it renders, Then the delta element is omitted', () => {
    host.delta = null;
    fixture.detectChanges();
    expect(q('.gsc-kpi__delta')).toBeNull();
  });
});
