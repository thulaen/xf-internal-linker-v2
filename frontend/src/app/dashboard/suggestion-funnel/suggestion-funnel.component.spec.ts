import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SuggestionFunnelComponent, FunnelStage } from './suggestion-funnel.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('SuggestionFunnelComponent', () => {
  let component: SuggestionFunnelComponent;
  let fixture: ComponentFixture<SuggestionFunnelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SuggestionFunnelComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(SuggestionFunnelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show message when no data', () => {
    fixture.componentRef.setInput('funnel', []);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.no-data')).toBeTruthy();
  });

  it('should render funnel stages', () => {
    const mockFunnel: FunnelStage[] = [
      { stage: 'Candidates', count: 1000 },
      { stage: 'Scored', count: 500, drop_reason: 'Low score' },
      { stage: 'Final', count: 100 }
    ];
    fixture.componentRef.setInput('funnel', mockFunnel);
    fixture.detectChanges();
    
    const stages = fixture.nativeElement.querySelectorAll('.funnel-stage');
    expect(stages.length).toBe(3);
    expect(stages[0].querySelector('.stage-count').textContent).toContain('1000');
    expect(stages[1].querySelector('.stage-drop').textContent).toContain('Low score');
  });

  it('should calculate bar width correctly', () => {
    component.funnel = [
      { stage: 'Max', count: 1000 },
      { stage: 'Half', count: 500 }
    ];
    expect(component.barWidth(1000)).toBe(100);
    expect(component.barWidth(500)).toBe(50);
    expect(component.barWidth(0)).toBe(8); // Minimum width
  });
});
