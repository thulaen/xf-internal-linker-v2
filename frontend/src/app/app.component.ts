import { CommonModule, DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, HostListener, OnInit, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterOutlet, RouterLink, RouterLinkActive, Router, NavigationEnd, ChildrenOutletContexts } from '@angular/router';
import { EMPTY, distinctUntilChanged, filter, fromEvent, map, Observable, startWith, switchMap, timer } from 'rxjs';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { MatBadgeModule } from '@angular/material/badge';
import { MatChipsModule } from '@angular/material/chips';
import { AlertDeliveryService } from './core/services/alert-delivery.service';
import { AppearanceService } from './core/services/appearance.service';
import { AuthService } from './core/services/auth.service';
import { GlobalLinkInterceptorService } from './core/services/global-link-interceptor.service';
import { HealthService, HealthSummary } from './health/health.service';
import { DashboardService, DashboardData } from './dashboard/dashboard.service';
import { PulseService, PulseState } from './core/services/pulse.service';
import { PerformanceModeService } from './core/services/performance-mode.service';
import { UserActivityService } from './core/services/user-activity.service';
import { SuggestionService } from './review/suggestion.service';
import { DiagnosticsService } from './diagnostics/diagnostics.service';
import { RouteAnnouncerService } from './core/services/route-announcer.service';
import { RouteFocusService } from './core/services/route-focus.service';
import { AnalyticsService } from './core/services/analytics.service';
import { NotificationCenterComponent } from './notification-center/notification-center.component';
import { ThemeCustomizerComponent } from './theme-customizer/theme-customizer.component';
import { ScrollToTopComponent } from './scroll-to-top/scroll-to-top.component';
import { ScrollHighlightDirective } from './core/directives/scroll-highlight.directive';
import { FreshnessBadgeComponent } from './shared/freshness-badge/freshness-badge.component';
import { HealthBannerComponent } from './shared/health-banner/health-banner.component';
import { OfflineBannerComponent } from './shared/offline-banner/offline-banner.component';
import { NavProgressBarComponent } from './shared/nav-progress-bar/nav-progress-bar.component';
import { CommandPaletteService } from './shared/services/command-palette.service';
import { ShortcutHelpService } from './shared/ui/shortcut-help/shortcut-help.service';
import { RealtimeService } from './core/services/realtime.service';
import { SessionTimeoutService } from './core/services/session-timeout.service';
import { DialogRouterService } from './core/services/dialog-router.service';
import { WebVitalsService } from './core/services/web-vitals.service';
import { ViewTransitionsService } from './core/services/view-transitions.service';
import { BackgroundSyncService } from './core/services/background-sync.service';
import { reportPlatformFeatures } from './core/util/platform-features';
import { A11yPrefsService } from './core/services/a11y-prefs.service';
import { LocaleService } from './core/services/locale.service';
import { FeatureFlagsService } from './core/services/feature-flags.service';
import { DebugOverlayComponent } from './shared/ui/debug-overlay/debug-overlay.component';
import { PresenceService } from './core/services/presence.service';
import { PresenceIndicatorComponent } from './shared/ui/presence-indicator/presence-indicator.component';
// Phase NV / Gaps 143-146 — Navigation Pro: breadcrumbs, recent pages,
// swipe-to-navigate. Tab persistence directive is exported separately
// because it attaches to <mat-tab-group> elements inside individual
// pages (settings, etc.), not the shell.
import { BreadcrumbsComponent } from './shared/ui/breadcrumbs/breadcrumbs.component';
import { RecentPagesMenuComponent } from './shared/ui/recent-pages-menu/recent-pages-menu.component';
import { RecentPagesService } from './core/services/recent-pages.service';
import { SwipeNavigateDirective } from './core/directives/swipe-navigate.directive';
// Phase GB / Gap 150 — onboarding state machine. Registered at boot so
// the Preference Center's progress meter has a known catalogue.
import {
  ONBOARDING_CATALOGUE,
  OnboardingStateService,
} from './core/services/onboarding-state.service';
// Phase GB / Gap 151 — feature-request dialog. Imported for MatDialog.open()
// when the toolbar "Suggest a feature" shortcut is invoked.
import { MatDialog } from '@angular/material/dialog';
import { FeatureRequestDialogComponent } from './shared/ui/feature-request-dialog/feature-request-dialog.component';
import { TutorialModeService } from './core/services/tutorial-mode.service';
import { ExplainModeService } from './core/services/explain-mode.service';
import { NoobModeService } from './core/services/noob-mode.service';
import { GlossaryService } from './shared/ui/glossary/glossary.service';
import { GlossaryDrawerComponent } from './shared/ui/glossary/glossary-drawer.component';
import { FaqDrawerComponent } from './shared/ui/faq-drawer/faq-drawer.component';
import { FaqService } from './shared/ui/faq-drawer/faq.service';
import { GuidedTourService, DASHBOARD_TOUR } from './core/services/guided-tour.service';
import { GuidedTourComponent } from './shared/ui/guided-tour/guided-tour.component';
import { BehaviorTrackerService } from './core/services/behavior-tracker.service';
import { EscapeHatchComponent } from './shared/ui/escape-hatch/escape-hatch.component';
import { HelpChatbotComponent } from './shared/ui/help-chatbot/help-chatbot.component';
import { routeTransitionAnimation } from './shared/animations/route-transition.animation';
import { environment } from '../environments/environment';
import { toSignal } from '@angular/core/rxjs-interop';
import { ConnectionStatus } from './core/services/realtime.types';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  tooltip: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule,
    MatMenuModule,
    NotificationCenterComponent,
    ThemeCustomizerComponent,
    ScrollToTopComponent,
    ScrollHighlightDirective,
    FreshnessBadgeComponent,
    HealthBannerComponent,
    OfflineBannerComponent,
    NavProgressBarComponent,
    MatBadgeModule,
    MatChipsModule,
    // Phase D2 — global UI surfaces always rendered by the shell.
    GlossaryDrawerComponent,
    FaqDrawerComponent,
    GuidedTourComponent,
    EscapeHatchComponent,
    HelpChatbotComponent,
    // Phase OB / Gap 133 — always mounted; renders nothing until Shift+D.
    DebugOverlayComponent,
    // Phase RC / Gap 139 — toolbar presence badge.
    PresenceIndicatorComponent,
    // Phase NV / Gaps 143, 144, 146 — breadcrumb bar, swipe directive,
    // recent-pages menu live in the shell template.
    BreadcrumbsComponent,
    RecentPagesMenuComponent,
    SwipeNavigateDirective,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  animations: [routeTransitionAnimation],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent implements OnInit {
  appearance = inject(AppearanceService);
  auth = inject(AuthService);
  private alertDelivery = inject(AlertDeliveryService);
  private healthService = inject(HealthService);
  private dashboardSvc = inject(DashboardService);
  private linkInterceptor = inject(GlobalLinkInterceptorService);
  private destroyRef = inject(DestroyRef);
  private cdr = inject(ChangeDetectorRef);
  private document = inject(DOCUMENT);
  private router = inject(Router);
  private pulseService = inject(PulseService);
  private suggestionSvc = inject(SuggestionService);
  private diagnosticsSvc = inject(DiagnosticsService);
  private routeAnnouncer = inject(RouteAnnouncerService);
  private routeFocus = inject(RouteFocusService);
  private analytics = inject(AnalyticsService);
  perfMode = inject(PerformanceModeService);
  private commandPalette = inject(CommandPaletteService);
  private shortcutHelp = inject(ShortcutHelpService);
  private realtimeSvc = inject(RealtimeService);
  private sessionTimeout = inject(SessionTimeoutService);
  private dialogRouter = inject(DialogRouterService);
  private webVitals = inject(WebVitalsService);
  private viewTransitions = inject(ViewTransitionsService);
  private bgSync = inject(BackgroundSyncService);
  // Phase A1 — accessibility + locale services. Services
  // self-initialise on first inject (effects in their constructors
  // mirror state to <html> attributes); no `start()` call needed.
  // Public so the toolbar template can read the signals.
  a11y = inject(A11yPrefsService);
  locale = inject(LocaleService);
  // Phase OB / Gaps 131 + 132 — feature-flag service. Start() kicks
  // the initial fetch; components read `isEnabled()` / `variantOf()`
  // anywhere.
  private featureFlags = inject(FeatureFlagsService);
  // Phase RC / Gap 139 — real-time presence of other operators.
  private presence = inject(PresenceService);
  // Phase NV / Gap 146 — auto-records every NavigationEnd; injection
  // alone is enough to keep the menu's history fresh.
  private recentPages = inject(RecentPagesService);
  // Phase GB / Gap 150 — onboarding progress for the preference center.
  private onboarding = inject(OnboardingStateService);
  // Phase GB / Gap 151 — open the feature-request dialog from the
  // toolbar "Suggest" button or from keyboard shortcut handlers.
  private dialog = inject(MatDialog);

  /** Phase A1 / Gap 99 — font-size choices the toolbar menu renders. */
  readonly fontSizeChoices = [90, 100, 115, 130] as const;
  /** Phase A1 / Gap 101 — colour-vision palette choices. */
  readonly cvdChoices = [
    { value: 'none' as const,        label: 'Off' },
    { value: 'protanopia' as const,  label: 'Protan' },
    { value: 'deuteranopia' as const,label: 'Deutan' },
    { value: 'tritanopia' as const,  label: 'Tritan' },
  ];
  // Phase D1 / Gaps 55 + 58 — toolbar toggles for Tutorial + Explain modes.
  // Public so the template can read the signal-based `enabled()`.
  tutorialMode = inject(TutorialModeService);
  explainMode = inject(ExplainModeService);
  // Phase D2 / Gaps 69, 70, 71, 73 — global services for noob UX.
  noobMode = inject(NoobModeService);
  glossary = inject(GlossaryService);
  faq = inject(FaqService);
  private tourSvc = inject(GuidedTourService);
  private behaviorTracker = inject(BehaviorTrackerService);
  private userActivity = inject(UserActivityService);
  private http = inject(HttpClient);
  private contexts = inject(ChildrenOutletContexts);
  private readonly pageVisible$ = fromEvent(this.document, 'visibilitychange').pipe(
    startWith(null),
    map(() => this.document.visibilityState === 'visible'),
    distinctUntilChanged(),
  );

  /** Gap 38 — WS connection status dot. Bound to the toolbar pill. */
  readonly wsStatus: ReturnType<typeof toSignal<ConnectionStatus>> =
    toSignal(this.realtimeSvc.connectionStatus$, { initialValue: 'offline' as ConnectionStatus });

  currentUser$ = this.auth.currentUser$;
  pulse: PulseState = { ok: false, status: 'unknown', lastBeatAt: 0, checks: {}, taskCount: 0 };

  // Freshness ribbon data
  lastSyncAt: string | null = null;
  lastAnalyticsAt: string | null = null;
  lastPipelineAt: string | null = null;
  runtimeMode = 'CPU';

  // Nav badge: pending suggestion count
  pendingSuggestionCount = 0;

  // Nav badge: unacknowledged ErrorLog rows on /diagnostics (Phase GT Step 12).
  unacknowledgedErrorCount = 0;

  // Hide the app shell on the login page so it gets its own minimal layout
  isLoginPage$ = this.router.events.pipe(
    filter(e => e instanceof NavigationEnd),
    map((e: NavigationEnd) => e.urlAfterRedirects.startsWith('/login')),
    startWith(this.router.url.startsWith('/login'))
  );

  customizerOpen = false;
  notifPanelOpen = false;
  openBrokenLinks = 0;
  systemStatus: 'healthy' | 'degraded' | 'critical' | 'unknown' = 'unknown';
  healthSummary: HealthSummary | null = null;
  masterPause = false;
  masterPauseBusy = false;

  navSections: NavSection[] = [
    {
      label: 'Main',
      items: [
        {
          label: 'Dashboard',
          icon: 'dashboard',
          route: '/dashboard',
          tooltip: 'Overview of jobs, suggestions, and key metrics',
        },
      ],
    },
    {
      label: 'Analysis',
      items: [
        {
          label: 'Review',
          icon: 'rate_review',
          route: '/review',
          tooltip: 'Review and approve link suggestions',
        },
        {
          label: 'Link Health',
          icon: 'link_off',
          route: '/link-health',
          tooltip: 'Broken link scanner and status tracker',
        },
        {
          label: 'Link Graph',
          icon: 'account_tree',
          route: '/graph',
          tooltip: 'Visualize the internal link graph',
        },
        {
          label: 'Behavioral Hubs',
          icon: 'hub',
          route: '/behavioral-hubs',
          tooltip: 'Co-navigation article clusters from GA4 session data',
        },
        {
          label: 'Analytics',
          icon: 'bar_chart',
          route: '/analytics',
          tooltip: 'SEO impact reports from GSC and GA4',
        },
      ],
    },
    {
      label: 'System',
      items: [
        {
          label: 'Jobs',
          icon: 'pending_actions',
          route: '/jobs',
          tooltip: 'Background job queue and history',
        },
        {
          label: 'System Health',
          icon: 'health_and_safety',
          route: '/health',
          tooltip: 'Real-time status of data sources and services',
        },
        {
          label: 'Settings',
          icon: 'settings',
          route: '/settings',
          tooltip: 'Theme, silo controls, and app settings',
        },
        {
          label: 'Alerts',
          icon: 'notifications',
          route: '/alerts',
          tooltip: 'Operator alert center',
        },
        {
          label: 'Web Crawler',
          icon: 'travel_explore',
          route: '/crawler',
          tooltip: 'Crawl your sites for SEO audit, broken links, and content discovery',
        },
        {
          label: 'Error Log',
          icon: 'bug_report',
          route: '/error-log',
          tooltip: 'Background job errors with plain-English explanations',
        },
        {
          label: 'Performance',
          icon: 'speed',
          route: '/performance',
          tooltip: 'Benchmark results for C++ and Python hot paths',
        },
        // Phase OF — Operations Feed (ambient narration stream).
        {
          label: 'Operations Feed',
          icon: 'rss_feed',
          route: '/operations-feed',
          tooltip: 'Live commentary of what the system is doing right now',
        },
        // Phase GB / Gap 149 — User Preference Center.
        {
          label: 'Preferences',
          icon: 'tune',
          route: '/preferences',
          tooltip: 'Appearance, language, accessibility, onboarding — all in one place',
        },
      ],
    },
  ];

  ngOnInit(): void {
    this.appearance.load();
    this.alertDelivery.start();
    this.linkInterceptor.init();
    // Phase GB / Gap 150 — register the milestone catalogue so the
    // Preference Center's progress meter has a known denominator.
    this.onboarding.registerCatalogue(ONBOARDING_CATALOGUE);
    // Item 13 — start listening for keyboard/mouse activity so "Until I come
    // back" can trigger an auto-revert once the user returns from idle.
    this.userActivity.start();
    // Phase U1 / Gap 23 — announce the current route to screen readers
    // on every NavigationEnd. No-op for sighted users.
    this.routeAnnouncer.start();
    // Phase U2 / Gap 22 — move keyboard focus to <main> or <h1> on
    // every NavigationEnd. Keyboard-only users skip chrome.
    this.routeFocus.start();
    // Phase U2 / Gap 25 — SPA-aware page-view analytics. Best-effort
    // dataLayer / gtag / Matomo push + future backend send.
    this.analytics.start();
    // Phase E2 / Gap 42 — warn 2 min before the long-lived token expires
    // so the user can extend without losing form state. Safe no-op if
    // the user is not currently signed in.
    this.sessionTimeout.start();
    // Phase E2 / Gap 45 — listen for ?dialog=<name> in the URL and reopen
    // the matching registered dialog. Per-page dialogs still register
    // themselves in their own ngOnInit.
    this.dialogRouter.start();
    // Phase E2 / Gap 51 — subscribe to LCP / CLS / INP / FCP / TTFB and
    // POST them to /api/telemetry/web-vitals/. Best-effort; silent on
    // network errors.
    this.webVitals.start();
    // Phase D2 / Gap 73 — record first daily route visits so the
    // Behavioral Nudge card can suggest a typical starting page.
    this.behaviorTracker.start();
    // Phase F1 / Gap 79 — wrap Angular router navigations in the
    // native View Transitions API so supported browsers crossfade
    // routes. Safe no-op on Firefox/Safari (no API).
    this.viewTransitions.start();
    // Phase F1 / Gap 88 — wire the offline write queue. When the
    // browser comes back online, queued POSTs are drained in FIFO.
    this.bgSync.start();
    // Phase F1 / Gaps 93 + 94 — log a one-time advisory when this
    // browser is missing the Popover API or the native <dialog>
    // element. Doesn't block features (everything has a Material
    // fallback), just helps diagnose unexpected UX on legacy clients.
    reportPlatformFeatures();
    // Phase OB / Gaps 131 + 132 — fetch the feature-flag snapshot.
    // Silent on 404 until the backend endpoint ships.
    this.featureFlags.start();
    // Phase RC / Gap 139 — heartbeat presence to other tabs.
    this.presence.start();

    this.startAuthenticatedPolls();
  }

  /**
   * Pollers that hit authenticated endpoints. Split from ngOnInit so each
   * method stays under the 80-line cap. All timers gate on isLoggedIn$:
   * while signed out (login page, startup token check) the timer is
   * replaced by EMPTY; on login the timer (re)starts from 0; on logout
   * it cancels cleanly so the server never sees a 403 storm.
   */
  private startAuthenticatedPolls(): void {
    // Toolbar performance-mode chip (2 min) + master-pause hydrate.
    this.whileLoggedInAndVisible(() =>
      timer(0, 2 * 60 * 1000).pipe(switchMap(() => this.perfMode.refresh())),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((rt) => {
        const anyRt = rt as any;
        if (typeof anyRt?.master_pause === 'boolean') {
          this.masterPause = anyRt.master_pause;
        }
        this.cdr.markForCheck();
      });

    // Broken-links badge + freshness ribbon — both read from the shared
    // dashboard cache so the shell does not fetch the same payload twice.
    this.dashboardSvc.data$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((data: DashboardData | null) => {
        this.openBrokenLinks = data?.open_broken_links ?? 0;
        this.lastSyncAt = data?.last_sync_at ?? null;
        this.lastPipelineAt = data?.last_pipeline_at ?? null;
        this.lastAnalyticsAt = data?.last_analytics_at ?? null;
        this.runtimeMode = data?.runtime_mode ?? 'CPU';
        this.cdr.markForCheck();
      });

    this.whileLoggedInAndVisible(() =>
      timer(0, 15 * 60 * 1000).pipe(switchMap(() => this.dashboardSvc.refresh())),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        error: () => {
          this.openBrokenLinks = 0;
          this.lastSyncAt = null;
          this.lastPipelineAt = null;
          this.lastAnalyticsAt = null;
          this.runtimeMode = 'CPU';
          this.cdr.markForCheck();
        },
      });

    this.pulseService.pulse$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((p) => {
        this.pulse = p;
        this.cdr.markForCheck();
      });

    // System-health summary for the status dot (30 min heartbeat).
    this.whileLoggedInAndVisible(() =>
      timer(0, 30 * 60 * 1000).pipe(switchMap(() => this.healthService.getSummary())),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (summary: HealthSummary) => {
          this.systemStatus = summary.system_status;
          this.healthSummary = summary;
          this.cdr.markForCheck();
        },
        error: () => {
          this.systemStatus = 'unknown';
          this.healthSummary = null;
          this.cdr.markForCheck();
        },
      });

    this.startNavBadgePolls();
  }

  /**
   * Phase GT Step 12 — sidenav badges for pending suggestions and
   * unacknowledged ErrorLog rows. Both poll every 5 minutes; the
   * realtime `diagnostics` topic doesn't fire on ErrorLog rows so we
   * keep the poll until a dedicated `errors.log` topic lands.
   */
  private startNavBadgePolls(): void {
    this.whileLoggedInAndVisible(() =>
      timer(0, 5 * 60 * 1000).pipe(switchMap(() => this.suggestionSvc.getPendingCount())),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (count: number) => {
          this.pendingSuggestionCount = count;
          this.cdr.markForCheck();
        },
        error: () => {
          this.pendingSuggestionCount = 0;
          this.cdr.markForCheck();
        },
      });

    this.whileLoggedInAndVisible(() =>
      timer(0, 5 * 60 * 1000).pipe(switchMap(() => this.diagnosticsSvc.getErrors())),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (errors) => {
          this.unacknowledgedErrorCount = Array.isArray(errors)
            ? errors.filter((e) => !e.acknowledged).length
            : 0;
          this.cdr.markForCheck();
        },
        error: () => {
          this.unacknowledgedErrorCount = 0;
          this.cdr.markForCheck();
        },
      });
  }

  /**
   * Shared gate: replace `seed()` with EMPTY while the user is signed
   * out. On login the caller's timer re-emits from zero; on logout the
   * switchMap cancels it cleanly.
   */
  private whileLoggedIn<T>(seed: () => Observable<T>): Observable<T> {
    return this.auth.isLoggedIn$.pipe(
      switchMap((loggedIn) => (loggedIn ? seed() : EMPTY)),
    );
  }

  private whileLoggedInAndVisible<T>(seed: () => Observable<T>): Observable<T> {
    return this.whileLoggedIn(() =>
      this.pageVisible$.pipe(
        switchMap((visible) => (visible ? seed() : EMPTY)),
      ),
    );
  }

  getRouteAnimationData(): string {
    return this.contexts.getContext('primary')?.route?.snapshot?.url?.toString() ?? '';
  }

  /**
   * Plan item 28 — "Pause Everything" master toggle.
   * Reads on boot inside the existing health-summary refresh cycle, flips on click.
   */
  toggleMasterPause(): void {
    if (this.masterPauseBusy) return;
    this.masterPauseBusy = true;
    this.http.post<{ master_pause: boolean }>('/api/settings/master-pause/', { paused: !this.masterPause })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.masterPause = !!res?.master_pause;
          this.masterPauseBusy = false;
          this.cdr.markForCheck();
        },
        error: () => {
          this.masterPauseBusy = false;
          this.cdr.markForCheck();
        },
      });
  }

  /** Severity level for the HealthBanner inside the status-dot popover. */
  get healthMenuSeverity(): 'info' | 'warning' | 'error' {
    if (this.systemStatus === 'critical') return 'error';
    if (this.systemStatus === 'degraded') return 'warning';
    return 'info';
  }

  /** Plain-English one-liner for the HealthBanner inside the status-dot popover. */
  get healthMenuMessage(): string {
    const count = this.healthSummary?.degraded_count ?? 0;
    switch (this.systemStatus) {
      case 'healthy': return 'All services are healthy.';
      case 'degraded': return `${count} service${count === 1 ? ' is' : 's are'} degraded.`;
      case 'critical': return `${count} service${count === 1 ? ' is' : 's are'} down or in error.`;
      default: return 'Health status unknown — click to run a full check.';
    }
  }

  /**
   * Open the Command Palette on Ctrl+K (Windows/Linux) or Cmd+K (Mac).
   * Re-pressing the shortcut while the palette is open closes it.
   */
  @HostListener('window:keydown', ['$event'])
  onGlobalKeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      this.commandPalette.toggle();
      return;
    }

    // Gap 34 — `?` opens the keyboard shortcut cheatsheet.
    // Ignore when the user is typing in an input, textarea, or select.
    if (
      event.key === '?' &&
      !event.ctrlKey &&
      !event.metaKey &&
      !event.altKey
    ) {
      const target = event.target as HTMLElement;
      const tag = target.tagName.toLowerCase();
      const editable = target.isContentEditable;
      if (tag !== 'input' && tag !== 'textarea' && tag !== 'select' && !editable) {
        event.preventDefault();
        this.shortcutHelp.toggle();
      }
    }

    // Phase D2 / Gap 69 — Alt+G toggles the glossary drawer.
    // Same input-typing guard as the `?` handler above.
    if (
      event.altKey &&
      !event.ctrlKey &&
      !event.metaKey &&
      event.key.toLowerCase() === 'g'
    ) {
      const target = event.target as HTMLElement;
      const tag = target.tagName.toLowerCase();
      const editable = target.isContentEditable;
      if (tag !== 'input' && tag !== 'textarea' && tag !== 'select' && !editable) {
        event.preventDefault();
        this.glossary.toggle();
      }
    }
  }

  /**
   * Phase D2 / Gap 70 — replay the dashboard guided tour from the
   * toolbar. Wired to the 🗺 button in the template.
   */
  startDashboardTour(): void {
    this.tourSvc.start(DASHBOARD_TOUR);
  }

  /**
   * Phase GB / Gap 151 — open the in-app "Suggest a feature" dialog.
   * Wired to the 💡 toolbar button. The dialog shows its own success /
   * error snackbars.
   */
  openFeatureRequestDialog(): void {
    this.dialog.open(FeatureRequestDialogComponent, {
      width: '520px',
      restoreFocus: true,
    });
  }

  get config() {
    return this.appearance.config;
  }

  get siteName(): string {
    return this.appearance.config.siteName;
  }

  goToAdmin(event: MouseEvent): void {
    event.preventDefault();
    window.open(environment.adminUrl, '_blank', 'noopener,noreferrer');
  }

  logout(): void {
    this.auth.logout();
  }

  /**
   * Phase E2 / Gap 40 — Skip-to-content link handler.
   *
   * Invoked by the visually-hidden `.skip-link` in the header when a
   * keyboard user presses Enter (or clicks). Moves focus to <main> so
   * subsequent Tab presses walk the page content, not the toolbar/sidenav.
   *
   * We intercept the click instead of relying on the default `href="#id"`
   * anchor behaviour because Angular routing can swallow the hash change
   * in some browsers, and native `:target` doesn't move focus — only
   * scroll position. `focus()` on an element with `tabindex="-1"` gives
   * us both scroll + keyboard focus in one call.
   */
  onSkipToContent(event: Event): void {
    event.preventDefault();
    const main = document.getElementById('main-content');
    if (!main) return;
    main.focus({ preventScroll: false });
  }
}
