// Shared primitives barrel export.
// Import from '@shared' or '../shared' in consuming components.

// ── Display components ─────────────────────────────────────────────
export { ExplainabilityTooltipComponent, ExplainabilityDialogComponent } from './explainability-tooltip/explainability-tooltip.component';
export { FreshnessBadgeComponent } from './freshness-badge/freshness-badge.component';
export { ConfidenceBadgeComponent } from './confidence-badge/confidence-badge.component';
export { EmptyStateComponent } from './empty-state/empty-state.component';
export { HealthBannerComponent } from './health-banner/health-banner.component';
export { PulseIndicatorComponent } from './components/pulse-indicator/pulse-indicator.component';

// ── Directives ─────────────────────────────────────────────────────
export { DeepLinkSpotlightDirective } from './directives/deep-link-spotlight.directive';
export { CardSpotlightDirective } from './directives/card-spotlight.directive';
export { DragOverDirective } from './directives/drag-over.directive';
export { MagneticButtonDirective } from './directives/magnetic-button.directive';

// ── Services ───────────────────────────────────────────────────────
export { NavigationCoordinatorService } from './services/navigation-coordinator.service';
export type { DeepLinkTarget } from './services/navigation-coordinator.service';

// ── Runbooks ───────────────────────────────────────────────────────
export { RUNBOOK_LIBRARY } from './runbooks/runbook-library';
export type { Runbook, RunbookStep } from './runbooks/runbook-library';
export { RunbookDialogComponent } from './runbooks/runbook-dialog/runbook-dialog.component';

// ── Animations ─────────────────────────────────────────────────────
export { buttonFeedbackAnimation } from './animations/button-feedback.animation';
