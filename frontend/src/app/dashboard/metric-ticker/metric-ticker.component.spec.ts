import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MetricTickerComponent } from './metric-ticker.component';
import { DashboardData } from '../dashboard.service';

describe('MetricTickerComponent', () => {
  let component: MetricTickerComponent;
  let fixture: ComponentFixture<MetricTickerComponent>;

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
      imports: [MetricTickerComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(MetricTickerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show 0 issues when healthy', () => {
    component.data = mockData;
    fixture.detectChanges();
    expect(component.issues()).toBe(0);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.mt-clear')).toBeTruthy();
  });

  it('should count down and warning services as issues', () => {
    component.data = {
      ...mockData,
      system_health: {
        ...mockData.system_health,
        summary: { 'down': 1, 'warning': 2, 'stale': 0 }
      }
    };
    fixture.detectChanges();
    expect(component.issues()).toBe(3);
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.mt-active')).toBeTruthy();
  });

  it('should include broken links in issues count', () => {
    component.data = mockData;
    component.openBrokenLinks = 5;
    fixture.detectChanges();
    expect(component.issues()).toBe(5);
  });
});
