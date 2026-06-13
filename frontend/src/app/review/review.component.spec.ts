import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ReviewComponent } from './review.component';
import { SuggestionService, Suggestion } from './suggestion.service';
import { of } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog } from '@angular/material/dialog';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('ReviewComponent', () => {
  let component: ReviewComponent;
  let fixture: ComponentFixture<ReviewComponent>;
  let suggestService: SpyObj<SuggestionService>;

  const mockSuggestion: Suggestion = {
    suggestion_id: 's1',
    status: 'pending',
    score_final: 0.9,
    destination: 1,
    destination_title: 'D1',
    destination_url: '',
    destination_content_type: 'thread',
    destination_source_label: 'XF',
    destination_silo_group: null,
    destination_silo_group_name: '',
    host: 2,
    host_title: 'H1',
    host_sentence_text: 'Context',
    host_content_type: 'thread',
    host_source_label: 'XF',
    host_silo_group: null,
    host_silo_group_name: '',
    same_silo: false,
    anchor_phrase: 'Anchor',
    anchor_edited: '',
    anchor_confidence: 'strong',
    repeated_anchor: false,
    rejection_reason: '',
    reviewed_at: null,
    is_applied: false,
    created_at: '2026-03-25T00:00:00Z',
  };

  beforeEach(async () => {
    suggestService = createSpyObj(['list', 'approve', 'reject', 'batchAction', 'startPipeline']);
    suggestService.list.mockReturnValue(of({ results: [mockSuggestion], count: 1, next: null, previous: null }));

    await TestBed.configureTestingModule({
      imports: [ReviewComponent, NoopAnimationsModule],
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        { provide: SuggestionService, useValue: suggestService },
        { provide: MatSnackBar, useValue: { open: () => {} } },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(null) }) } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ReviewComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should reload the list if an approved suggestion no longer matches the filter', () => {
    component.statusFilter = 'pending';
    component.suggestions.set([{ ...mockSuggestion }]);
    const loadSpy = vi.spyOn(component, 'load');

    // Simulate quickApprove success
    const updatedSuggestion = { ...mockSuggestion, status: 'approved' as const };
    suggestService.approve.mockReturnValue(of(updatedSuggestion as any));

    component.quickApprove(mockSuggestion, new MouseEvent('click'));

    expect(loadSpy).toHaveBeenCalled();
  });

  it('should NOT reload the list if we are in the "all" filter', () => {
    component.statusFilter = 'all';
    component.suggestions.set([{ ...mockSuggestion }]);
    const loadSpy = vi.spyOn(component, 'load');

    // Simulate quickApprove success
    const updatedSuggestion = { ...mockSuggestion, status: 'approved' as const };
    suggestService.approve.mockReturnValue(of(updatedSuggestion as any));

    component.quickApprove(mockSuggestion, new MouseEvent('click'));

    expect(loadSpy).not.toHaveBeenCalled();
    expect(component.suggestions()[0].status).toBe('approved');
  });

  it('should load suggestions on init', () => {
    expect(suggestService.list).toHaveBeenCalled();
    expect(component.suggestions().length).toBe(1);
  });

  it('should quickApprove a suggestion', () => {
    const updatedSuggestion = { ...mockSuggestion, status: 'approved' as const };
    suggestService.approve.mockReturnValue(of(updatedSuggestion as any));

    component.quickApprove(mockSuggestion, new MouseEvent('click'));

    expect(suggestService.approve).toHaveBeenCalledWith('s1');
  });

  it('should quickReject a suggestion with reason', () => {
    const updatedSuggestion = { ...mockSuggestion, status: 'rejected' as const };
    suggestService.reject.mockReturnValue(of(updatedSuggestion as any));

    component.quickReject(mockSuggestion, 'duplicate', new MouseEvent('click'));

    expect(suggestService.reject).toHaveBeenCalledWith('s1', 'duplicate');
  });

  it('should toggle selection of suggestions', () => {
    component.toggleSelect('s1');
    expect(component.isSelected('s1')).toBe(true);

    component.toggleSelect('s1');
    expect(component.isSelected('s1')).toBe(false);
  });

  it('should select all suggestions on current page', () => {
    component.suggestions.set([
      { ...mockSuggestion, suggestion_id: 's1' },
      { ...mockSuggestion, suggestion_id: 's2' },
    ]);

    component.toggleSelectAll();

    expect(component.allSelected()).toBe(true);
    expect(component.isSelected('s1')).toBe(true);
    expect(component.isSelected('s2')).toBe(true);
  });

  it('should clear all selections', () => {
    component.selectedIds.set(new Set(['s1', 's2']));
    component.clearSelection();
    expect(component.selectedIds().size).toBe(0);
  });

  it('should batch approve selected suggestions', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    component.selectedIds.set(new Set(['s1', 's2']));
    suggestService.batchAction.mockReturnValue(of({ updated: 2 }));

    component.batchApprove();

    expect(suggestService.batchAction).toHaveBeenCalledWith('approve', ['s1', 's2']);
  });

  it('should batch reject selected suggestions', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    component.selectedIds.set(new Set(['s1', 's2']));
    suggestService.batchAction.mockReturnValue(of({ updated: 2 }));

    component.batchReject('duplicate');

    expect(suggestService.batchAction).toHaveBeenCalledWith('reject', ['s1', 's2'], 'duplicate');
  });

  it('should compute scoreColor based on score', () => {
    expect(component.scoreColor(0.9)).toBe('high');
    expect(component.scoreColor(0.6)).toBe('medium');
    expect(component.scoreColor(0.4)).toBe('low');
  });

  it('should calculate daysWaiting since created_at', () => {
    const pastDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const days = component.daysWaiting(pastDate.toISOString());
    expect(days).toBe(7);
  });

  it('should determine aging level based on days', () => {
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);

    expect(component.agingLevel(thirtyDaysAgo.toISOString())).toBe('red');
    expect(component.agingLevel(sevenDaysAgo.toISOString())).toBe('amber');
    expect(component.agingLevel(twoDaysAgo.toISOString())).toBe('neutral');
  });

  it('should map anchor_confidence to confidence level', () => {
    const s1 = { ...mockSuggestion, score_final: 0.9, anchor_confidence: 'strong' as const };
    const s2 = { ...mockSuggestion, score_final: 0.9, anchor_confidence: 'weak' as const };
    const s3 = { ...mockSuggestion, score_final: 0.3, anchor_confidence: 'strong' as const };

    expect(component.confidenceLevel(s1 as any)).toBe('high');
    expect(component.confidenceLevel(s2 as any)).toBe('medium');
    expect(component.confidenceLevel(s3 as any)).toBe('thin');
  });

  it('should identify suggestions needing human judgment', () => {
    const needsJudgment = { ...mockSuggestion, score_final: 0.6, anchor_confidence: 'strong' as const };
    const doesNotNeed = { ...mockSuggestion, score_final: 0.9, anchor_confidence: 'strong' as const };

    expect(component.needsHumanJudgment(needsJudgment as any)).toBe(true);
    expect(component.needsHumanJudgment(doesNotNeed as any)).toBe(false);
  });

  it('should provide silo label', () => {
    expect(component.siloLabel('MySilo')).toBe('MySilo');
    expect(component.siloLabel('')).toBe('Unassigned');
  });

  it('should track by suggestion id', () => {
    const id = component.trackById(0, mockSuggestion);
    expect(id).toBe('s1');
  });
});
