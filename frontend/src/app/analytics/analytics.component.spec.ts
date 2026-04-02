import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';

import { AnalyticsComponent } from './analytics.component';
import { AnalyticsService } from './analytics.service';

describe('AnalyticsComponent', () => {
  const analyticsServiceStub = {
    getOverview: () => of({
      ga4: {
        connection_status: 'saved',
        connection_message: 'Saved.',
        read_connection_status: 'connected',
        read_connection_message: 'Read sync worked.',
        last_sync: null,
      },
      matomo: {
        connection_status: 'not_configured',
        connection_message: 'Not set up.',
        last_sync: null,
      },
      totals_last_30_days: {
        impressions: 0,
        clicks: 0,
        destination_views: 0,
        engaged_sessions: 0,
        conversions: 0,
      },
      telemetry_row_count: 0,
      coverage_row_count: 0,
      latest_coverage: null,
    }),
    getIntegration: () => of({
      status: 'ready' as const,
      message: 'Copy this browser snippet into the live site.',
      event_schema: 'fr016_v1',
      ga4_browser_ready: true,
      matomo_browser_ready: false,
      session_ttl_minutes: 30,
      install_steps: ['Paste the script.'],
      browser_snippet: '<script>window.test=true;</script>',
    }),
    getHealth: jasmine.createSpy('getHealth').and.returnValue(of({
      days: 30,
      overall: {
        row_count: 2,
        latest_state: 'partial' as const,
        latest_date: '2026-04-02',
        event_schema: 'fr016_v1',
        healthy_days: 1,
        partial_days: 1,
        degraded_days: 0,
        expected_instrumented_links: 20,
        observed_impression_links: 15,
        observed_click_links: 10,
        attributed_destination_sessions: 9,
        unattributed_destination_sessions: 3,
        duplicate_event_drops: 2,
        missing_metadata_events: 1,
        delayed_rows_rewritten: 4,
        impression_coverage_rate: 0.75,
        click_coverage_rate: 0.5,
        attribution_rate: 0.75,
      },
      sources: [
        {
          source_label: 'ga4',
          row_count: 1,
          latest_state: 'partial' as const,
          latest_date: '2026-04-02',
          event_schema: 'fr016_v1',
          healthy_days: 0,
          partial_days: 1,
          degraded_days: 0,
          expected_instrumented_links: 10,
          observed_impression_links: 8,
          observed_click_links: 5,
          attributed_destination_sessions: 6,
          unattributed_destination_sessions: 2,
          duplicate_event_drops: 2,
          missing_metadata_events: 1,
          delayed_rows_rewritten: 3,
          impression_coverage_rate: 0.8,
          click_coverage_rate: 0.5,
          attribution_rate: 0.75,
        },
      ],
    })),
    getBreakdowns: jasmine.createSpy('getBreakdowns').and.returnValue(of({
      days: 30,
      selected_source: 'all' as const,
      device_categories: [
        {
          label: 'mobile',
          impressions: 12,
          clicks: 5,
          engaged_sessions: 3,
          ctr: 0.4167,
        },
      ],
      channel_groups: [
        {
          label: 'Organic Search',
          impressions: 12,
          clicks: 5,
          engaged_sessions: 3,
          ctr: 0.4167,
        },
      ],
      countries: [
        {
          label: 'United Kingdom',
          impressions: 12,
          clicks: 5,
          engaged_sessions: 3,
          ctr: 0.4167,
        },
      ],
    })),
    getFunnel: jasmine.createSpy('getFunnel').and.returnValue(of({
      days: 30,
      selected_source: 'all' as const,
      totals: {
        impressions: 10,
        clicks: 4,
        destination_views: 3,
        engaged_sessions: 2,
        conversions: 1,
      },
      by_source: [
        {
          telemetry_source: 'ga4' as const,
          impressions: 5,
          clicks: 2,
          destination_views: 2,
          engaged_sessions: 1,
          conversions: 0,
        },
      ],
    })),
    getTrend: jasmine.createSpy('getTrend').and.returnValue(of({
      days: 30,
      selected_source: 'all' as const,
      items: [
        {
          date: '2026-04-02',
          impressions: 10,
          clicks: 4,
          destination_views: 3,
          engaged_sessions: 2,
          conversions: 1,
          ctr: 0.4,
          engagement_rate: 0.6667,
        },
      ],
    })),
    getTopSuggestions: jasmine.createSpy('getTopSuggestions').and.returnValue(of({
      days: 30,
      selected_source: 'all' as const,
      items: [
        {
          suggestion_id: '11111111-1111-1111-1111-111111111111',
          telemetry_source: 'matomo' as const,
          destination_title: 'Destination Thread',
          anchor_phrase: 'host',
          status: 'pending',
          impressions: 10,
          clicks: 4,
          destination_views: 3,
          engaged_sessions: 2,
          conversions: 1,
          ctr: 0.4,
          engagement_rate: 0.6667,
        },
      ],
    })),
    runGa4Sync: jasmine.createSpy('runGa4Sync').and.returnValue(of({
      sync_run_id: 1,
      task_id: 'task-ga4',
      source: 'ga4' as const,
      status: 'queued',
      message: 'GA4 telemetry sync queued.',
    })),
    runMatomoSync: jasmine.createSpy('runMatomoSync').and.returnValue(of({
      sync_run_id: 2,
      task_id: 'task-matomo',
      source: 'matomo' as const,
      status: 'queued',
      message: 'Matomo telemetry sync queued.',
    })),
  };

  beforeEach(() => {
    analyticsServiceStub.runGa4Sync.calls.reset();
    analyticsServiceStub.runMatomoSync.calls.reset();
    analyticsServiceStub.getFunnel.calls.reset();
    analyticsServiceStub.getHealth.calls.reset();
    analyticsServiceStub.getBreakdowns.calls.reset();
    analyticsServiceStub.getTrend.calls.reset();
    analyticsServiceStub.getTopSuggestions.calls.reset();
  });

  it('shows the live-site browser bridge card', async () => {
    await TestBed.configureTestingModule({
      imports: [AnalyticsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: AnalyticsService,
          useValue: analyticsServiceStub,
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AnalyticsComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Live-site browser bridge');
    expect(fixture.nativeElement.textContent).toContain('Ready to install');
    expect(fixture.nativeElement.textContent).toContain('Copy browser snippet');
    expect(fixture.nativeElement.textContent).toContain('Run Matomo sync');
    expect(fixture.nativeElement.textContent).toContain('Run GA4 sync');
    expect(fixture.nativeElement.textContent).toContain('Funnel for the last 30 days');
    expect(fixture.nativeElement.textContent).toContain('Telemetry health for the last 30 days');
    expect(fixture.nativeElement.textContent).toContain('Impression coverage');
    expect(fixture.nativeElement.textContent).toContain('Device mix');
    expect(fixture.nativeElement.textContent).toContain('Channel mix');
    expect(fixture.nativeElement.textContent).toContain('Country mix');
    expect(fixture.nativeElement.textContent).toContain('Top suggestion rows');
  });

  it('queues manual syncs from the page buttons', async () => {
    await TestBed.configureTestingModule({
      imports: [AnalyticsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: AnalyticsService,
          useValue: analyticsServiceStub,
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AnalyticsComponent);
    fixture.detectChanges();

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    const matomoButton = buttons.find((button) => button.textContent?.includes('Run Matomo sync'));
    const ga4Button = buttons.find((button) => button.textContent?.includes('Run GA4 sync'));

    matomoButton?.click();
    ga4Button?.click();

    expect(analyticsServiceStub.runMatomoSync).toHaveBeenCalled();
    expect(analyticsServiceStub.runGa4Sync).toHaveBeenCalled();
  });

  it('reloads report queries when the source filter changes', async () => {
    await TestBed.configureTestingModule({
      imports: [AnalyticsComponent, NoopAnimationsModule],
      providers: [
        {
          provide: AnalyticsService,
          useValue: analyticsServiceStub,
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(AnalyticsComponent);
    fixture.detectChanges();

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('.source-filter button')) as HTMLButtonElement[];
    const ga4Button = buttons.find((button) => button.textContent?.includes('GA4 only'));
    ga4Button?.click();

    expect(analyticsServiceStub.getFunnel).toHaveBeenCalledWith('ga4');
    expect(analyticsServiceStub.getBreakdowns).toHaveBeenCalledWith('ga4');
    expect(analyticsServiceStub.getTrend).toHaveBeenCalledWith('ga4');
    expect(analyticsServiceStub.getTopSuggestions).toHaveBeenCalledWith('ga4');
  });
});
