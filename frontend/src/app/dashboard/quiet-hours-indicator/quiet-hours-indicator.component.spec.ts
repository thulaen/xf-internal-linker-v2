import { ComponentFixture, TestBed } from '@angular/core/testing';
import { QuietHoursIndicatorComponent } from './quiet-hours-indicator.component';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { of } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('QuietHoursIndicatorComponent', () => {
  let component: QuietHoursIndicatorComponent;
  let fixture: ComponentFixture<QuietHoursIndicatorComponent>;
  let mockVisibility: SpyObj<VisibilityGateService>;

  beforeEach(async () => {
    mockVisibility = createSpyObj(['whileLoggedInAndVisible']);
    mockVisibility.whileLoggedInAndVisible.mockReturnValue(of());

    await TestBed.configureTestingModule({
      imports: [QuietHoursIndicatorComponent, NoopAnimationsModule],
      providers: [
        { provide: VisibilityGateService, useValue: mockVisibility }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(QuietHoursIndicatorComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should correctly identify quiet hours (same day)', () => {
    component.start.set('09:00');
    component.end.set('17:00');
    component.enabled.set(true);

    const morning = new Date();
    morning.setHours(10, 0);
    component.now.set(morning);
    expect(component.isQuiet()).toBe(true);

    const evening = new Date();
    evening.setHours(18, 0);
    component.now.set(evening);
    expect(component.isQuiet()).toBe(false);
  });

  it('should correctly identify quiet hours (across midnight)', () => {
    component.start.set('22:00');
    component.end.set('06:00');
    component.enabled.set(true);

    const night = new Date();
    night.setHours(23, 0);
    component.now.set(night);
    expect(component.isQuiet()).toBe(true);

    const earlyMorning = new Date();
    earlyMorning.setHours(2, 0);
    component.now.set(earlyMorning);
    expect(component.isQuiet()).toBe(true);

    const day = new Date();
    day.setHours(10, 0);
    component.now.set(day);
    expect(component.isQuiet()).toBe(false);
  });

  it('should return false if disabled', () => {
    component.start.set('00:00');
    component.end.set('23:59');
    component.enabled.set(false);
    expect(component.isQuiet()).toBe(false);
  });

  it('should enter and exit edit mode', () => {
    fixture.detectChanges();
    expect(component.editing()).toBe(false);
    
    component.startEdit();
    expect(component.editing()).toBe(true);
    
    component.cancelEdit();
    expect(component.editing()).toBe(false);
  });

  it('should save drafts to actual values', () => {
    fixture.detectChanges();
    component.startEdit();
    component.startDraft = '11:00';
    component.endDraft = '12:00';
    component.save(new Event('submit'));
    
    expect(component.start()).toBe('11:00');
    expect(component.end()).toBe('12:00');
    expect(component.editing()).toBe(false);
  });
});
