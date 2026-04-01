import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReviewComponent } from './review.component';
import { SuggestionService, Suggestion } from './suggestion.service';
import { of } from 'rxjs';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatDialog } from '@angular/material/dialog';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('ReviewComponent', () => {
  let component: ReviewComponent;
  let fixture: ComponentFixture<ReviewComponent>;
  let suggestService: jasmine.SpyObj<SuggestionService>;

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
    suggestService = jasmine.createSpyObj('SuggestionService', ['list', 'approve', 'reject', 'batchAction', 'startPipeline']);
    suggestService.list.and.returnValue(of({ results: [mockSuggestion], count: 1, next: null, previous: null }));

    await TestBed.configureTestingModule({
      imports: [ReviewComponent, NoopAnimationsModule],
      providers: [
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
    component.suggestions = [{ ...mockSuggestion }];
    const loadSpy = spyOn(component, 'load').and.callThrough();

    // Simulate quickApprove success
    const updatedSuggestion = { ...mockSuggestion, status: 'approved' as const };
    suggestService.approve.and.returnValue(of(updatedSuggestion as any));

    component.quickApprove(mockSuggestion, new MouseEvent('click'));

    expect(loadSpy).toHaveBeenCalled();
  });

  it('should NOT reload the list if we are in the "all" filter', () => {
    component.statusFilter = 'all';
    component.suggestions = [{ ...mockSuggestion }];
    const loadSpy = spyOn(component, 'load').and.callThrough();

    // Simulate quickApprove success
    const updatedSuggestion = { ...mockSuggestion, status: 'approved' as const };
    suggestService.approve.and.returnValue(of(updatedSuggestion as any));

    component.quickApprove(mockSuggestion, new MouseEvent('click'));

    expect(loadSpy).not.toHaveBeenCalled();
    expect(component.suggestions[0].status).toBe('approved');
  });
});
