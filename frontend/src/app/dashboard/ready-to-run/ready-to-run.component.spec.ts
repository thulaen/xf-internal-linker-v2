import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReadyToRunComponent } from './ready-to-run.component';
import { RouterTestingModule } from '@angular/router/testing';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';

describe('ReadyToRunComponent', () => {
  let component: ReadyToRunComponent;
  let fixture: ComponentFixture<ReadyToRunComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        RouterTestingModule,
        MatCardModule,
        MatIconModule,
        MatButtonModule,
        MatTooltipModule,
        ReadyToRunComponent
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ReadyToRunComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show green level for healthy system and recent run', () => {
    component.health = { status: 'healthy' };
    component.lastRunDaysAgo = 2;
    expect(component.gateLevel).toBe('green');
    expect(component.gateMessage).toBe('Ready to run the pipeline.');
  });

  it('should show amber level if last run was long ago', () => {
    component.health = { status: 'healthy' };
    component.lastRunDaysAgo = 10;
    expect(component.gateLevel).toBe('amber');
    expect(component.gateMessage).toBe('Check a few things before running.');
    expect(component.blockers.some(b => b.label.includes('10 days ago'))).toBeTrue();
  });

  it('should show red level for error status', () => {
    component.health = { status: 'error' };
    expect(component.gateLevel).toBe('red');
    expect(component.gateMessage).toBe('Fix issues before running the pipeline.');
    expect(component.blockers.some(b => b.label === 'System health is degraded')).toBeTrue();
  });

  it('should render blocker rows', () => {
    fixture.componentRef.setInput('health', { status: 'stale' });
    fixture.detectChanges();
    const rows = fixture.nativeElement.querySelectorAll('.blocker-row');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0].textContent).toContain('Data may be stale');
  });
});
