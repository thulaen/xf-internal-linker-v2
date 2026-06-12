import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PickUpComponent, ResumeState } from './pick-up.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

describe('PickUpComponent', () => {
  let component: PickUpComponent;
  let fixture: ComponentFixture<PickUpComponent>;

  const mockResumeState: ResumeState = {
    interrupted_runs: [{ run_id: '1234567890', run_state: 'stalled' }],
    resumable_syncs: [],
    missed_tasks: [{ task_name: 'Weekly Backup', weight_class: 'heavy', hours_overdue: 24, reason: 'Worker timeout' }]
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PickUpComponent, EmptyStateComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(PickUpComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show empty state when no items to resume', () => {
    component.resumeState = { interrupted_runs: [], resumable_syncs: [], missed_tasks: [] };
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('app-empty-state')).toBeTruthy();
  });

  it('should render interrupted runs', () => {
    fixture.componentRef.setInput('resumeState', { ...mockResumeState });
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll('.resume-row');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('Pipeline 12345678');
  });

  it('should emit resumeRun when Resume is clicked', () => {
    vi.spyOn(component.resumeRun, 'emit').mockReturnValue(undefined as never);
    fixture.componentRef.setInput('resumeState', { ...mockResumeState });
    fixture.detectChanges();

    const resumeBtn = fixture.nativeElement.querySelector('button[mat-stroked-button]');
    expect(resumeBtn).toBeTruthy();
    resumeBtn.click();
    expect(component.resumeRun.emit).toHaveBeenCalledWith('1234567890');
  });
});
