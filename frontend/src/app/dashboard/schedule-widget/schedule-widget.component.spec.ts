import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ScheduleWidgetComponent } from './schedule-widget.component';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { of } from 'rxjs';

describe('ScheduleWidgetComponent', () => {
  let component: ScheduleWidgetComponent;
  let fixture: ComponentFixture<ScheduleWidgetComponent>;
  let mockVisibility: jasmine.SpyObj<VisibilityGateService>;

  beforeEach(async () => {
    mockVisibility = jasmine.createSpyObj('VisibilityGateService', ['whileLoggedInAndVisible']);
    mockVisibility.whileLoggedInAndVisible.and.returnValue(of());

    await TestBed.configureTestingModule({
      imports: [ScheduleWidgetComponent],
      providers: [
        { provide: VisibilityGateService, useValue: mockVisibility }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ScheduleWidgetComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should render the today summary', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.sw-summary-value')?.textContent).toContain('task');
  });

  it('should render the next task if one exists', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.sw-next-row')).toBeTruthy();
  });

  it('should format minutes correctly', () => {
    expect(component.formatMinutes(0)).toBe('less than a minute');
    expect(component.formatMinutes(45)).toBe('45 min');
    expect(component.formatMinutes(60)).toBe('1h');
    expect(component.formatMinutes(75)).toBe('1h 15m');
  });

  it('should update the next task calculation when time changes', () => {
    // Pipeline sync is hourly at :00.
    // Set time to 10:45. Next is 11:00 (15 mins away).
    const t1 = new Date();
    t1.setHours(10, 45, 0, 0);
    component.now.set(t1);
    fixture.detectChanges();
    
    // We can't easily assert on the computed's inner result if it's private,
    // but we can check the DOM.
    const compiled = fixture.nativeElement as HTMLElement;
    // Look for "in 15 min" (might vary if other tasks are closer, e.g. glitchtip at :00/:30)
    // GlitchTip at 10:45: next is 11:00 (15 mins).
    // Pipeline at 10:45: next is 11:00 (15 mins).
    expect(compiled.querySelector('.sw-next-when')?.textContent).toContain('in 15 min');
  });
});
