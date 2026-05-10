import { ComponentFixture, TestBed } from '@angular/core/testing';
import { InstantHealthComponent } from './instant-health.component';
import { DashboardData } from '../dashboard.service';

describe('InstantHealthComponent', () => {
  let component: InstantHealthComponent;
  let fixture: ComponentFixture<InstantHealthComponent>;

  const mockData: DashboardData = {
    system_health: {
      status: 'healthy',
      summary: { 'down': 0, 'warning': 0, 'stale': 0 },
      total_monitored: 0
    },
    suggestion_counts: { pending: 0, approved: 0, applied: 0, rejected: 0, total: 0 },
    content_count: 100,
    open_broken_links: 0,
    pipeline_runs: [],
    recent_imports: [],
    last_sync: null,
    show_quick_controls: false
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [InstantHealthComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(InstantHealthComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show YES when healthy', () => {
    component.data = mockData;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.ih-verdict')?.textContent).toContain('YES');
    expect(component.verdict()).toBe('good');
  });

  it('should show ATTENTION when there are warnings', () => {
    component.data = {
      ...mockData,
      system_health: {
        ...mockData.system_health,
        summary: { 'down': 0, 'warning': 1, 'stale': 0 }
      }
    };
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.ih-verdict')?.textContent).toContain('ATTENTION');
    expect(component.verdict()).toBe('warn');
  });

  it('should show NO when there are down services', () => {
    component.data = {
      ...mockData,
      system_health: {
        ...mockData.system_health,
        summary: { 'down': 1, 'warning': 0, 'stale': 0 }
      }
    };
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.ih-verdict')?.textContent).toContain('NO');
    expect(component.verdict()).toBe('bad');
  });

  it('should show NO when there are urgent alerts', () => {
    component.data = mockData;
    component.urgentAlertCount = 1;
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.ih-verdict')?.textContent).toContain('NO');
    expect(component.verdict()).toBe('bad');
  });
});
