import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EngagementMixComponent } from './engagement-mix.component';
import { AnalyticsService, AnalyticsEngagementMixResponse } from '../analytics.service';
import { Subject } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ChangeDetectorRef } from '@angular/core';

describe('EngagementMixComponent', () => {
  let component: EngagementMixComponent;
  let fixture: ComponentFixture<EngagementMixComponent>;
  let analyticsService: SpyObj<AnalyticsService>;
  let responseSubject: Subject<AnalyticsEngagementMixResponse>;

  const mockData: AnalyticsEngagementMixResponse = {
    days: 30,
    selected_source: 'all',
    totals: {
      destination_views: 1000,
      engaged_sessions: 400,
      quick_exit_sessions: 100,
      dwell_30s_sessions: 250,
      dwell_60s_sessions: 150
    },
    rates: {
      quick_exit_rate: 0.1,
      engaged_rate: 0.4,
      dwell_30s_rate: 0.25,
      dwell_60s_rate: 0.15
    }
  };

  beforeEach(async () => {
    responseSubject = new Subject<AnalyticsEngagementMixResponse>();
    analyticsService = createSpyObj(['getEngagementMix']);
    analyticsService.getEngagementMix.mockReturnValue(responseSubject.asObservable());

    await TestBed.configureTestingModule({
      imports: [EngagementMixComponent, NoopAnimationsModule],
      providers: [
        { provide: AnalyticsService, useValue: analyticsService }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(EngagementMixComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show loading spinner while fetching data', () => {
    expect(component.loading).toBe(true);
    const spinner = fixture.nativeElement.querySelector('mat-spinner');
    expect(spinner).toBeTruthy();
  });

  it('should render KPI tiles when data is loaded', () => {
    responseSubject.next(mockData);
    // For OnPush, we often need to trigger change detection explicitly on the cdr
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    const tiles = fixture.nativeElement.querySelectorAll('.kpi-tile');
    expect(tiles.length).toBe(4);
  });

  it('should show empty hint if views are zero', () => {
    const emptyData: AnalyticsEngagementMixResponse = {
      ...mockData,
      totals: { ...mockData.totals, destination_views: 0 }
    };
    responseSubject.next(emptyData);
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    const emptyHint = fixture.nativeElement.querySelector('.empty-hint');
    expect(emptyHint).toBeTruthy();
    expect(emptyHint.textContent).toContain('No destination views yet');
  });

  it('should handle error from service gracefully', () => {
    responseSubject.error(new Error('API Error'));
    const cdr = fixture.componentRef.injector.get(ChangeDetectorRef);
    cdr.detectChanges();

    expect(component.loading).toBe(false);
    expect(component.data).toBeNull();
  });
});
