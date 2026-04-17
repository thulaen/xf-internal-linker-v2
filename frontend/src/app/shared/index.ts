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
// Phase E2 / Gap 50 — Character counter for inputs / textareas.
export { CharCounterDirective } from './directives/char-counter.directive';
// Phase D3 / Gap 178 — hover-to-define jargon underline directive.
export { JargonDirective } from './directives/jargon.directive';
// Phase A1 / Gaps 106 + 108 — locale-aware Intl pipes.
export { IntlNumberPipe, IntlCurrencyPipe, IntlDatePipe, IntlDateTimePipe } from './pipes/intl.pipes';
export { TimeAgoPipe } from './pipes/time-ago.pipe';

// ── Phase FR / Gaps 109-116 — Forms primitives ────────────────────
// Gap 109 — multi-step wizard.
export {
  FormWizardComponent,
  FormWizardStepComponent,
  WizardStepContentDirective,
} from './wizard/wizard.component';
// Gap 110 — form draft autosave (drop on <form>).
export { FormAutosaveDirective } from './directives/form-autosave.directive';
// Gap 111 — submit-time error summary at top of form.
export { FormErrorSummaryComponent } from './ui/form-error-summary/form-error-summary.component';
// Gap 112 — per-field smart defaults.
export { SmartDefaultDirective } from './directives/smart-default.directive';
// Gap 113 — green ✓ on valid+touched controls.
export { ValidCheckmarkDirective } from './directives/valid-checkmark.directive';
// Gap 114 — × clear-field button (use as matSuffix).
export { ClearFieldButtonComponent } from './ui/clear-field-button/clear-field-button.component';
// Gap 115 — show-password eye toggle (drop on <input type="password">).
export { PasswordRevealDirective } from './directives/password-reveal.directive';
// Gap 116 — drag-reorder list field.
export { ReorderListComponent } from './ui/reorder-list/reorder-list.component';

// ── Phase DC / Gaps 117-129 — Data & Collaboration primitives ─────
// Gap 117 — old → new diff preview.
export { DiffPreviewComponent } from './ui/diff-preview/diff-preview.component';
// Gap 118 — per-entity audit trail viewer.
export { AuditTrailComponent } from './ui/audit-trail/audit-trail.component';
// Gap 120 + 121 — bulk selection state + action toolbar.
export { BulkSelection } from './bulk-selection/bulk-selection';
export { BulkActionToolbarComponent } from './ui/bulk-action-toolbar/bulk-action-toolbar.component';
// Gap 122 + 123 — drag/drop + paste-to-upload dropzone.
export { DropzoneComponent } from './ui/dropzone/dropzone.component';
// Gap 124 — markdown editor + preview.
export { MarkdownEditorComponent } from './ui/markdown-editor/markdown-editor.component';
export { renderMarkdown } from './ui/markdown-editor/markdown-render';
// Gap 125 — code editor (JSON/YAML/text).
export { CodeEditorComponent } from './ui/code-editor/code-editor.component';
// Gap 126 — CSV importer with column mapping.
export { CsvImporterComponent } from './ui/csv-importer/csv-importer.component';
export type { CsvFieldSpec } from './ui/csv-importer/csv-importer.component';
// Gap 127 — share-link dialog.
export { ShareLinkDialogComponent } from './ui/share-link/share-link-dialog.component';
export type { ShareLinkDialogData, ShareLinkResponse } from './ui/share-link/share-link-dialog.component';
// Gap 128 + 129 — comments with @mentions.
export { CommentsComponent } from './ui/comments/comments.component';

// ── Services ───────────────────────────────────────────────────────
export { NavigationCoordinatorService } from './services/navigation-coordinator.service';
export type { DeepLinkTarget } from './services/navigation-coordinator.service';
export { CommandPaletteService } from './services/command-palette.service';
export { COMMANDS } from './services/command-palette.commands';
export type { Command } from './services/command-palette.commands';
export { CommandPaletteComponent } from './components/command-palette/command-palette.component';

// ── Phase E1 — new shared primitives ──────────────────────────────
// Gap 30 — Confirm dialog
export { ConfirmDialogComponent } from './confirm-dialog/confirm-dialog.component';
export { ConfirmService } from './confirm-dialog/confirm.service';
export type { ConfirmDialogData } from './confirm-dialog/confirm-dialog.component';

// Gap 34 — Shortcut help modal
export { ShortcutHelpComponent } from './ui/shortcut-help/shortcut-help.component';
export { ShortcutHelpService } from './ui/shortcut-help/shortcut-help.service';

// Gap 35 — Copy-to-clipboard button
export { CopyButtonComponent } from './ui/copy-button/copy-button.component';

// Gap 37 — Staleness indicator
export { UpdatedAgoComponent } from './ui/updated-ago/updated-ago.component';

// ── Runbooks ───────────────────────────────────────────────────────
export { RUNBOOK_LIBRARY } from './runbooks/runbook-library';
export type { Runbook, RunbookStep } from './runbooks/runbook-library';
export { RunbookDialogComponent } from './runbooks/runbook-dialog/runbook-dialog.component';

// ── Animations ─────────────────────────────────────────────────────
export { buttonFeedbackAnimation } from './animations/button-feedback.animation';

// Phase E2 / Gap 44 — Back-to-top FAB consolidation.
// Re-exports the existing ScrollToTopComponent (which already uses OnPush
// and auto-detects the `.page-content` container) so pages with their own
// scrollable panes can drop `<app-scroll-to-top [scrollTarget]="ref">`
// without reaching outside the `@shared` barrel.
export { ScrollToTopComponent } from '../scroll-to-top/scroll-to-top.component';

// Phase E2 / Gap 46 — CSV / JSON export menu for any data table.
export { ExportMenuComponent } from './data-export/export-menu.component';
