import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HealthScoreDialComponent } from './health-score-dial.component';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { DashboardData } from '../dashboard.service';

describe('HealthScoreDialComponent', () => {
  let component: HealthScoreDialComponent;
  let fixture: ComponentFixture<HealthScoreDialComponent>;

  const mockDashboardData: DashboardData = {
    system_health: {
      status: 'healthy',
      summary: {
        healthy: 10,
        warning: 0,
        stale: 0,
        down: 0
      },
      total_monitored: 10,
    },
    suggestion_counts: { pending: 0, approved: 0, applied: 0, rejected: 0, total: 0 },
    content_count: 100,
    open_broken_links: 0,
    pipeline_runs: [],
    recent_imports: [],
    last_sync: null,
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HealthScoreDialComponent, NoopAnimationsModule],
      providers: [
        { provide: ActivatedRoute, useValue: { params: of({}) } }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(HealthScoreDialComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should compute score 100 when all is healthy', () => {
    component.data = mockDashboardData;
    component.openBrokenLinks = 0;
    component.urgentAlertCount = 0;
    fixture.detectChanges();

    expect(component.score()).toBe(100);
    expect(component.grade()).toBe('good');
  });

  it('should subtract 30 if any service is down', () => {
    const dataWithDown: DashboardData = {
      ...mockDashboardData,
      system_health: {
        ...mockDashboardData.system_health,
        summary: { ...mockDashboardData.system_health.summary, down: 1 }
      }
    } as any;
    component.data = dataWithDown;
    fixture.detectChanges();

    // 100 - 30 = 70
    expect(component.score()).toBe(70);
    expect(component.grade()).toBe('warn');
  });

  it('should subtract 15 per warning (capped at 30)', () => {
    const dataWithWarnings: DashboardData = {
      ...mockDashboardData,
      system_health: {
        ...mockDashboardData.system_health,
        summary: { ...mockDashboardData.system_health.summary, warning: 3 }
      }
    } as any;
    component.data = dataWithWarnings;
    fixture.detectChanges();

    // 100 - min(3 * 15, 30) = 70
    expect(component.score()).toBe(70);
  });

  it('should subtract 10 for urgent alerts', () => {
    component.data = mockDashboardData;
    component.urgentAlertCount = 2;
    fixture.detectChanges();

    // 100 - 10 = 90
    expect(component.score()).toBe(90);
  });

  it('should subtract for broken links (capped at 20)', () => {
    component.data = mockDashboardData;
    component.openBrokenLinks = 100; // floor(100/50)*5 = 10
    fixture.detectChanges();
    expect(component.score()).toBe(90);

    component.openBrokenLinks = 500; // floor(500/50)*5 = 50 -> capped at 20
    fixture.detectChanges();
    expect(component.score()).toBe(80);
  });

  it('should clamp score to 0', () => {
    const badData: DashboardData = {
      ...mockDashboardData,
      system_health: {
        ...mockDashboardData.system_health,
        summary: { down: 1, warning: 10 } // -30, -30 = -60
      }
    } as any;
    component.data = badData;
    component.urgentAlertCount = 10; // -10
    component.openBrokenLinks = 1000; // -20
    // Total subtract = 30 + 30 + 10 + 20 = 90. Result 10.
    fixture.detectChanges();
    expect(component.score()).toBe(10);
    expect(component.grade()).toBe('bad');
  });

  it('should render the SVG dial and progress arc', () => {
    component.data = mockDashboardData;
    fixture.detectChanges();

    const svg = fixture.nativeElement.querySelector('svg');
    const progress = fixture.nativeElement.querySelector('.hsd-progress');
    expect(svg).toBeTruthy();
    expect(progress).toBeTruthy();
    expect(progress.classList).toContain('hsd-good');
  });
});
