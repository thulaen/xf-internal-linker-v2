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
});
