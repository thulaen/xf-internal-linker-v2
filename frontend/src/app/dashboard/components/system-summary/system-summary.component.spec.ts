import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SystemSummaryComponent } from './system-summary.component';
import { MatIconModule } from '@angular/material/icon';
import { RouterTestingModule } from '@angular/router/testing';

describe('SystemSummaryComponent', () => {
  let component: SystemSummaryComponent;
  let fixture: ComponentFixture<SystemSummaryComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SystemSummaryComponent, MatIconModule, RouterTestingModule]
    }).compileComponents();

    fixture = TestBed.createComponent(SystemSummaryComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should not render when health is null', () => {
    component.health = null;
    fixture.detectChanges();
    const card = fixture.nativeElement.querySelector('.system-summary-card');
    expect(card).toBeNull();
  });

  it('should render healthy state correctly', () => {
    component.health = {
      status: 'healthy',
      summary: { healthy: 10, warning: 0, error: 0, down: 0, stale: 0 },
      total_monitored: 10
    };
    fixture.detectChanges();

    const icon = fixture.nativeElement.querySelector('.icon-base');
    expect(icon.textContent).toContain('check_circle');
    expect(icon.classList).toContain('status-healthy');

    const counts = fixture.nativeElement.querySelectorAll('.count');
    expect(counts[0].textContent).toContain('10'); // Healthy
    expect(counts[1].textContent).toContain('0');  // Warning
    expect(counts[2].textContent).toContain('0');  // Critical
  });

  it('should render warning state with active indicators', () => {
    component.health = {
      status: 'warning',
      summary: { healthy: 8, warning: 2, error: 0, down: 0, stale: 0 },
      total_monitored: 10
    };
    fixture.detectChanges();

    const icon = fixture.nativeElement.querySelector('.icon-base');
    expect(icon.textContent).toContain('warning');
    expect(icon.classList).toContain('status-warning');

    const warningItem = fixture.nativeElement.querySelector('.status-item.warning');
    expect(warningItem.classList).toContain('active');
    expect(warningItem.querySelector('.count').textContent).toContain('2');
  });

  it('should render critical state correctly', () => {
    component.health = {
      status: 'error',
      summary: { healthy: 7, warning: 1, error: 1, down: 1, stale: 0 },
      total_monitored: 10
    };
    fixture.detectChanges();

    const icon = fixture.nativeElement.querySelector('.icon-base');
    expect(icon.textContent).toContain('error');
    
    const criticalItem = fixture.nativeElement.querySelector('.status-item.critical');
    expect(criticalItem.classList).toContain('active');
    expect(criticalItem.querySelector('.count').textContent).toContain('2'); // error + down
  });
});
