import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TrafficWorkbenchComponent, WowTelemetryRow } from './traffic-workbench.component';

/** Helper to create a row with a given change_pct. */
const row = (change_pct: number, title = 'Page'): WowTelemetryRow =>
  ({ change_pct, title } as WowTelemetryRow);

describe('TrafficWorkbenchComponent', () => {
  let fixture: ComponentFixture<TrafficWorkbenchComponent>;
  let component: TrafficWorkbenchComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TrafficWorkbenchComponent],
      providers: [provideNoopAnimations()],
    }).compileComponents();
    fixture = TestBed.createComponent(TrafficWorkbenchComponent);
    component = fixture.componentInstance;
  });

  it('renders without error when no data is supplied', () => {
    component.telemetryData = [];
    fixture.detectChanges();
    expect(fixture.nativeElement).toBeTruthy();
  });

  it('shows empty hint when no rows exceed ±30% threshold', () => {
    component.telemetryData = [row(10), row(-5), row(29)];
    fixture.detectChanges();
    const hint = fixture.nativeElement.querySelector('.empty-hint');
    expect(hint).toBeTruthy();
    expect(hint.textContent).toContain('30%');
  });

  it('renders only rows that exceed ±30% threshold', () => {
    component.telemetryData = [
      row(45, 'Rising'),
      row(-35, 'Falling'),
      row(5, 'Stable'),
      row(31, 'Just over'),
    ];
    fixture.detectChanges();
    expect(component.filteredRows.length).toBe(3);
  });

  it('does not show empty hint when matching rows exist', () => {
    component.telemetryData = [row(50, 'Big mover')];
    fixture.detectChanges();
    const hint = fixture.nativeElement.querySelector('.empty-hint');
    expect(hint).toBeNull();
    const cards = fixture.nativeElement.querySelectorAll('.workbench-card');
    expect(cards.length).toBeGreaterThan(0);
  });

  it('applies arrow-up class for positive change', () => {
    component.telemetryData = [row(50, 'Up')];
    fixture.detectChanges();
    const icon = fixture.nativeElement.querySelector('mat-icon.arrow-up');
    expect(icon).toBeTruthy();
  });

  it('applies arrow-down class for negative change', () => {
    component.telemetryData = [row(-50, 'Down')];
    fixture.detectChanges();
    const icon = fixture.nativeElement.querySelector('mat-icon.arrow-down');
    expect(icon).toBeTruthy();
  });

  it('sorts rows by absolute change value descending', () => {
    component.telemetryData = [row(35), row(50), row(-45)];
    fixture.detectChanges();
    expect(component.filteredRows[0].change_pct).toBe(50);
    expect(component.filteredRows[1].change_pct).toBe(-45);
    expect(component.filteredRows[2].change_pct).toBe(35);
  });

  it('displays page title in row', () => {
    component.telemetryData = [row(40, 'My Page Title')];
    fixture.detectChanges();
    const title = fixture.nativeElement.querySelector('.row-title');
    expect(title.textContent).toContain('My Page Title');
  });

  it('formats percentage change with + sign for positive', () => {
    component.telemetryData = [row(45.7)];
    fixture.detectChanges();
    const delta = fixture.nativeElement.querySelector('.delta-pos');
    expect(delta.textContent).toContain('+');
    expect(delta.textContent).toContain('45.7%');
  });

  it('applies delta-pos class for positive change', () => {
    component.telemetryData = [row(40)];
    fixture.detectChanges();
    const delta = fixture.nativeElement.querySelector('[class*="delta-"]');
    expect(delta.classList.contains('delta-pos')).toBe(true);
  });

  it('applies delta-neg class for negative change', () => {
    component.telemetryData = [row(-40)];
    fixture.detectChanges();
    const delta = fixture.nativeElement.querySelector('[class*="delta-"]');
    expect(delta.classList.contains('delta-neg')).toBe(true);
  });
});
