import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { SuggestionService, SuggestionDetail, REJECTION_REASONS } from './suggestion.service';
import { HighlightPipe } from '../core/pipes/highlight.pipe';

export interface DialogData {
  suggestionId: string;
}

export type DialogResult =
  | { action: 'approved' | 'rejected' | 'applied'; suggestion: SuggestionDetail }
  | null;


@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-suggestion-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatChipsModule,
    MatDialogModule,
    MatDividerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
    HighlightPipe,
  ],
  templateUrl: './suggestion-detail-dialog.component.html',
  styleUrls: ['./suggestion-detail-dialog.component.scss'],
})
export class SuggestionDetailDialogComponent implements OnInit {
  detail: SuggestionDetail | null = null;
  loading = true;
  error = '';
  saving = false;

  // Editable fields
  anchorEdited = '';
  reviewerNotes = '';
  rejectionReason = 'irrelevant';

  rejectionMode = false;
  readonly rejectionReasons = REJECTION_REASONS;

  readonly dialogRef = inject(MatDialogRef) as MatDialogRef<SuggestionDetailDialogComponent, DialogResult>;
  readonly data: DialogData = inject(MAT_DIALOG_DATA);
  private svc = inject(SuggestionService);
  private snack = inject(MatSnackBar);

  ngOnInit(): void {
    this.svc.getDetail(this.data.suggestionId).subscribe({
      next: (d) => {
        this.detail = d;
        this.anchorEdited = d.anchor_edited || d.anchor_phrase;
        this.reviewerNotes = d.reviewer_notes ?? '';
        this.loading = false;
      },
      error: () => {
        this.error = 'Failed to load suggestion details.';
        this.loading = false;
      },
    });
  }

  get effectiveAnchor(): string {
    return this.detail?.anchor_edited || this.detail?.anchor_phrase || '';
  }


  scorePercent(val: number): number {
    return Math.max(0, Math.min(100, Math.round(val * 100)));
  }

  phraseSummary(): string {
    const diagnostics = this.detail?.phrase_match_diagnostics;
    if (!diagnostics) {
      return 'Neutral means the sentence did not provide useful phrase evidence.';
    }
    if (diagnostics.selected_match_type === 'partial') {
      return 'Partial means the sentence matched part of the destination phrase and nearby words supported it.';
    }
    if (diagnostics.selected_match_type === 'exact') {
      return 'Phrase relevance means the host sentence contains a destination phrase or a close local phrase match.';
    }
    return 'Neutral means the sentence did not provide useful phrase evidence.';
  }

  phraseStateLabel(): string {
    const state = this.detail?.phrase_match_diagnostics?.phrase_match_state ?? 'neutral_no_host_match';
    if (state === 'computed_exact_title') {
      return 'Exact title phrase';
    }
    if (state === 'computed_exact_distilled') {
      return 'Exact distilled-text phrase';
    }
    if (state === 'computed_partial_title') {
      return 'Partial title phrase';
    }
    if (state === 'computed_partial_distilled') {
      return 'Partial distilled-text phrase';
    }
    if (state === 'fallback_current_extractor') {
      return 'Fallback to current exact-title extractor';
    }
    if (state === 'neutral_no_destination_phrases') {
      return 'Neutral / no usable destination phrases';
    }
    if (state === 'neutral_partial_below_threshold') {
      return 'Neutral / partial phrase below threshold';
    }
    return 'Neutral / no useful phrase match';
  }

  linkFreshnessSummary(): string {
    const diagnostics = this.detail?.link_freshness_diagnostics;
    if (!diagnostics) {
      return 'Neutral means there is not enough link history yet.';
    }
    if (diagnostics.freshness_bucket === 'fresh') {
      return 'Fresh means this destination has newer or growing inbound links.';
    }
    if (diagnostics.freshness_bucket === 'stale') {
      return 'Stale means newer inbound-link growth has cooled off or links have recently disappeared.';
    }
    return 'Neutral means there is not enough link history yet.';
  }

  linkFreshnessStateLabel(): string {
    const state = this.detail?.link_freshness_diagnostics?.freshness_data_state ?? 'neutral_missing_history';
    if (state === 'computed') {
      return 'Computed from stored link history';
    }
    if (state === 'neutral_thin_history') {
      return 'Neutral / not enough link history';
    }
    if (state === 'neutral_invalid_history') {
      return 'Neutral / invalid link history';
    }
    return 'Neutral / not enough link history';
  }

  learnedAnchorSummary(): string {
    const diagnostics = this.detail?.learned_anchor_diagnostics;
    if (!diagnostics) {
      return 'Neutral means the site does not have enough clean anchor history yet.';
    }
    if (diagnostics.learned_anchor_state === 'exact_variant_match' || diagnostics.learned_anchor_state === 'family_match') {
      return 'Corroborated means the chosen anchor looks like wording the site already uses for this destination.';
    }
    if (diagnostics.learned_anchor_state === 'host_contains_canonical_variant') {
      return 'The sentence already contains a learned site pattern, but this version only reports it and does not auto-swap the anchor.';
    }
    return 'Neutral means the site does not have enough clean anchor history yet.';
  }

  learnedAnchorStateLabel(): string {
    const state = this.detail?.learned_anchor_diagnostics?.learned_anchor_state ?? 'neutral_no_learned_anchor_data';
    if (state === 'exact_variant_match') {
      return 'Exact learned-anchor match';
    }
    if (state === 'family_match') {
      return 'Learned-anchor family match';
    }
    if (state === 'host_contains_canonical_variant') {
      return 'Sentence contains a learned canonical anchor';
    }
    if (state === 'neutral_no_anchor_candidate') {
      return 'Neutral / no anchor candidate';
    }
    if (state === 'neutral_below_min_sources') {
      return 'Neutral / not enough clean anchor sources';
    }
    if (state === 'neutral_processing_error') {
      return 'Neutral / learned-anchor processing error';
    }
    return 'Neutral / no useful learned-anchor evidence';
  }

  learnedAnchorFamiliesSummary(): string {
    const families = this.detail?.learned_anchor_diagnostics?.top_learned_families ?? [];
    return families
      .slice(0, 3)
      .map((family) => {
        const alternates = family.alternate_variants.length
          ? ` (alts: ${family.alternate_variants.slice(0, 3).join(', ')})`
          : '';
        return `${family.canonical_anchor}${alternates}`;
      })
      .join(' - ');
  }

  hasRareTermDiagnostics(): boolean {
    return !!this.detail?.rare_term_diagnostics?.rare_term_state;
  }

  rareTermSummary(): string {
    const state = this.detail?.rare_term_diagnostics?.rare_term_state;
    if (state === 'computed_match') {
      return 'Rare-term propagation means this sentence uses a rare word that nearby related pages use for this topic.';
    }
    if (state === 'neutral_feature_disabled') {
      return 'Rare-term propagation is turned off, so this score stays neutral.';
    }
    return 'Neutral means there was not enough safe related-page evidence to borrow terms.';
  }

  rareTermStateLabel(): string {
    const state = this.detail?.rare_term_diagnostics?.rare_term_state ?? 'neutral_no_eligible_related_pages';
    if (state === 'computed_match') {
      return 'Matched a safely borrowed rare term';
    }
    if (state === 'neutral_feature_disabled') {
      return 'Neutral / feature turned off';
    }
    if (state === 'neutral_no_eligible_related_pages') {
      return 'Neutral / no safe related pages';
    }
    if (state === 'neutral_no_rare_terms') {
      return 'Neutral / no usable borrowed terms';
    }
    if (state === 'neutral_below_min_support') {
      return 'Neutral / not enough related-page support';
    }
    if (state === 'neutral_processing_error') {
      return 'Neutral / rare-term processing error';
    }
    return 'Neutral / no host match';
  }

  rareTermMatchedTermsSummary(): string {
    const matches = this.detail?.rare_term_diagnostics?.matched_propagated_terms ?? [];
    return matches
      .slice(0, 2)
      .map((match) => `${match.term} (${match.supporting_related_pages} pages)`)
      .join(' - ');
  }

  rareTermTopTermsSummary(): string {
    const terms = this.detail?.rare_term_diagnostics?.top_propagated_terms ?? [];
    return terms
      .slice(0, 3)
      .map((term) => term.term)
      .join(' - ');
  }

  fieldAwareSummary(): string {
    const diagnostics = this.detail?.field_aware_diagnostics;
    if (!diagnostics) {
      return 'Neutral means the sentence did not line up with the destination fields in a useful way.';
    }
    if (diagnostics.field_aware_state === 'computed_match') {
      return 'Field-aware relevance checks where the sentence lines up with the destination title, body, scope labels, and learned anchor wording.';
    }
    if (diagnostics.field_aware_state === 'neutral_no_destination_terms') {
      return 'Neutral means the destination did not have enough usable field text.';
    }
    if (diagnostics.field_aware_state === 'neutral_no_host_terms') {
      return 'Neutral means the host sentence did not have enough useful words.';
    }
    if (diagnostics.field_aware_state === 'neutral_processing_error') {
      return 'Neutral means the field-aware scorer hit a processing error.';
    }
    return 'Neutral means the sentence did not line up with the destination fields in a useful way.';
  }

  fieldAwareStateLabel(): string {
    const state = this.detail?.field_aware_diagnostics?.field_aware_state ?? 'neutral_no_field_matches';
    if (state === 'computed_match') {
      return 'Matched destination fields';
    }
    if (state === 'neutral_no_destination_terms') {
      return 'Neutral / no usable destination field text';
    }
    if (state === 'neutral_no_host_terms') {
      return 'Neutral / no useful host terms';
    }
    if (state === 'neutral_processing_error') {
      return 'Neutral / field-aware processing error';
    }
    return 'Neutral / no useful field matches';
  }

  fieldAwareMatchedFieldsSummary(): string {
    const diagnostics = this.detail?.field_aware_diagnostics;
    if (!diagnostics) {
      return '';
    }
    const labels: Array<[keyof typeof diagnostics.field_scores, string]> = [
      ['title', 'title'],
      ['body', 'body'],
      ['scope', 'scope'],
      ['learned_anchor', 'learned anchors'],
    ];
    return labels
      .filter(([key]) => (diagnostics.field_scores[key]?.score ?? 0) > 0)
      .map(([key, label]) => `${label} ${(diagnostics.field_scores[key].score * 100).toFixed(0)}`)
      .join(' - ');
  }

  fieldAwareTopTerms(fieldName: 'title' | 'body' | 'scope' | 'learned_anchor'): string {
    const terms = this.detail?.field_aware_diagnostics?.field_scores?.[fieldName]?.matched_terms ?? [];
    return terms
      .slice(0, 3)
      .map((term) => term.token)
      .join(' - ');
  }

  clickDistanceSummary(): string {
    const diagnostics = this.detail?.click_distance_diagnostics;
    if (!diagnostics) {
      return 'Neutral means no structural depth data is available for this destination.';
    }
    if (diagnostics.click_distance_state === 'computed') {
      const parts = [];
      if (diagnostics.click_distance > 0) parts.push(`Click distance: ${diagnostics.click_distance}`);
      if (diagnostics.url_depth > 0) parts.push(`URL depth: ${diagnostics.url_depth}`);
      return `Prioritizes structurally shallower pages. ${parts.join(', ')}. Combined depth score: ${diagnostics.combined_depth.toFixed(2)}.`;
    }
    return 'Neutral means no structural depth data is available for this destination.';
  }

  clickDistanceStateLabel(): string {
    const state = this.detail?.click_distance_diagnostics?.click_distance_state ?? 'neutral_missing_tree';
    if (state === 'computed') {
      return 'Computed structural depth';
    }
    if (state === 'neutral_missing_tree') {
      return 'Neutral / missing scope tree';
    }
    if (state === 'neutral_root_path') {
      return 'Neutral / root path (homepage)';
    }
    if (state === 'neutral_no_depth') {
      return 'Neutral / no depth detected';
    }
    if (state === 'neutral_processing_error') {
      return 'Neutral / structural prior error';
    }
    return 'Neutral / no structural prior data';
  }

  clusteringSummary(): string {
    const diagnostics = this.detail?.cluster_diagnostics;
    if (!diagnostics) {
      return 'Neutral means no clustering data is available for this destination.';
    }
    const state = diagnostics.clustering_state;
    if (state === 'suppressed_non_canonical') {
      return `This is a near-duplicate of "${diagnostics.canonical_title}". It is suppressed (-${diagnostics.suppression_penalty} points) to favor the canonical version.`;
    }
    if (state === 'boosted_canonical') {
      const others = diagnostics.member_count - 1;
      return `This is the canonical representative for a cluster of ${diagnostics.member_count} similar items. ${others} duplicate(s) were suppressed.`;
    }
    return 'Neutral means this item is unique or clustering was not applied.';
  }

  clusteringStateLabel(): string {
    const state = this.detail?.cluster_diagnostics?.clustering_state ?? 'neutral_no_cluster';
    switch (state) {
      case 'suppressed_non_canonical': return 'Suppressed Duplicate';
      case 'boosted_canonical': return 'Canonical Representative';
      case 'neutral_no_cluster': return 'Unique Result';
      case 'neutral_clustering_disabled': return 'Clustering Disabled';
      case 'neutral_processing_error': return 'Clustering Error';
      default: return 'Unique Result';
    }
  }

  feedbackRerankSummary(): string {
    const diagnostics = this.detail?.explore_exploit_diagnostics;
    if (!diagnostics) {
      return 'Neutral means no historical feedback data was used for this suggestion.';
    }
    const state = diagnostics.rerank_state;
    if (state === 'computed_applied') {
      const exploitIdx = (diagnostics.exploit_score * 100).toFixed(0);
      const exploreIdx = (diagnostics.explore_score * 100).toFixed(0);
      return `Reranked using historical performance. Success rate (Bayesian): ${exploitIdx}%. Exploration bonus (UCB1): +${exploreIdx}%. Based on ${diagnostics.total_attempts} attempts.`;
    }
    if (state === 'neutral_feature_disabled') {
       return 'Feedback-driven reranking is currently disabled in settings.';
    }
    return 'Neutral means no historical feedback data was used for this suggestion.';
  }

  feedbackRerankStateLabel(): string {
    const state = this.detail?.explore_exploit_diagnostics?.rerank_state ?? 'neutral_no_historical_data';
    switch (state) {
      case 'computed_applied': return 'Feedback-driven optimization applied';
      case 'neutral_no_historical_data': return 'Neutral / no historical data for this pair';
      case 'neutral_feature_disabled': return 'Neutral / feature disabled';
      case 'neutral_processing_error': return 'Neutral / processing error';
      default: return 'Neutral / no historical data';
    }
  }

  slateDiversitySummary(): string {
    const diagnostics = this.detail?.slate_diversity_diagnostics;
    if (!diagnostics?.mmr_applied) {
      return 'This suggestion did not go through the final diversity reranker.';
    }
    if ((diagnostics.slot ?? 0) === 0) {
      return 'This was the first pick for its host, so it won on raw relevance before any diversity penalty was needed.';
    }
    if (diagnostics.swapped_from_rank) {
      return 'The diversity pass moved this suggestion up because it gave the host thread a more varied final set of links.';
    }
    return 'The diversity pass checked this suggestion against already-picked destinations for the same host thread.';
  }

  slateDiversityStateLabel(): string {
    const diagnostics = this.detail?.slate_diversity_diagnostics;
    if (!diagnostics?.mmr_applied) {
      return 'Diversity reranker not applied';
    }
    if ((diagnostics.slot ?? 0) === 0) {
      return 'Top relevance pick';
    }
    if (diagnostics.swapped_from_rank) {
      return 'Promoted for variety';
    }
    return 'Kept after diversity check';
  }

  slateDiversityRuntimeLabel(): string {
    const runtimePath = this.detail?.slate_diversity_diagnostics?.runtime_path;
    return runtimePath === 'cpp_extension' ? 'C++ fast path' : 'Python fallback';
  }

  graphWalkSummary(): string {
    const diagnostics = this.detail?.graph_walk_diagnostics;
    if (!diagnostics) {
      return 'Neutral means this candidate was found via direct embedding search only.';
    }
    if (diagnostics.nodes_visited > 100) {
      return `Graph discovery (Pixie) found this candidate after ${diagnostics.walk_steps} walk steps across ${diagnostics.nodes_visited} nodes.`;
    }
    return 'Neutral means the graph walk did not provide strong enough evidence for this pair.';
  }

  graphWalkStateLabel(): string {
    const origin = this.detail?.candidate_origin;
    if (origin === 'graph_walk') return 'Discovered via Knowledge Graph';
    if (origin === 'both') return 'Strong Bridge (Vector + Graph)';
    return 'Vector Search Candidate';
  }

  valueModelSummary(): string {
    const diagnostics = this.detail?.value_model_diagnostics;
    if (!diagnostics?.enabled) {
      return 'Value model was disabled or skipped for this candidate.';
    }
    const score = (diagnostics.score_value * 100).toFixed(0);
    return `Predicted link value: ${score}/100. This candidate was prioritised because it has strong potential for user engagement (traffic + relevance).`;
  }

  valueModelStateLabel(): string {
    const score = this.detail?.score_value_model ?? 0;
    if (score > 0.7) return 'High Expected Value';
    if (score > 0.4) return 'Moderate Value';
    return 'Low Value / Pruned';
  }

  telemetryStatusLabel(): string {
    const status = this.detail?.telemetry_instrumentation?.status ?? 'unknown';
    if (status === 'instrumented') return 'Instrumented markup ready';
    if (status === 'plain_manual') return 'Plain manual only';
    return 'Unknown';
  }

  async copyInstrumentedMarkup(): Promise<void> {
    const markup = this.detail?.telemetry_instrumentation?.instrumented_markup ?? '';
    if (!markup) {
      this.snack.open('This suggestion does not have enough data to build telemetry-ready markup yet.', 'Dismiss', { duration: 4000 });
      return;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(markup);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = markup;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      this.snack.open('Telemetry-ready link markup copied.', undefined, { duration: 2500 });
    } catch {
      this.snack.open('Could not copy the markup automatically.', 'Dismiss', { duration: 4000 });
    }
  }

  approve(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.approve(this.detail.suggestion_id, this.anchorEdited, this.reviewerNotes).subscribe({
      next: (s) => this.dialogRef.close({ action: 'approved', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Approve failed.'; },
    });
  }

  startReject(): void {
    this.rejectionMode = true;
  }

  confirmReject(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.reject(this.detail.suggestion_id, this.rejectionReason, this.reviewerNotes).subscribe({
      next: (s) => this.dialogRef.close({ action: 'rejected', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Reject failed.'; },
    });
  }

  apply(): void {
    if (!this.detail || this.saving) return;
    this.saving = true;
    this.svc.apply(this.detail.suggestion_id).subscribe({
      next: (s) => this.dialogRef.close({ action: 'applied', suggestion: s }),
      error: () => { this.saving = false; this.error = 'Apply failed.'; },
    });
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}
