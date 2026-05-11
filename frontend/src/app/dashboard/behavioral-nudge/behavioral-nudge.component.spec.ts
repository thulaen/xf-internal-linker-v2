import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { BehavioralNudgeComponent } from './behavioral-nudge.component';
import { BehaviorTrackerService } from '../../core/services/behavior-tracker.service';

describe('BehavioralNudgeComponent', () => {
  let component: BehavioralNudgeComponent;
  let fixture: ComponentFixture<BehavioralNudgeComponent>;
  let mockTracker: jasmine.SpyObj<BehaviorTrackerService>;

  beforeEach(async () => {
    mockTracker = jasmine.createSpyObj('BehaviorTrackerService', ['getMostVisitedRoute']);

    await TestBed.configureTestingModule({
      imports: [BehavioralNudgeComponent],
      providers: [
        { provide: BehaviorTrackerService, useValue: mockTracker },
        provideRouter([])
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(BehavioralNudgeComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    mockTracker.getMostVisitedRoute.and.returnValue(null);
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should be hidden when no suggestion is available', () => {
    mockTracker.getMostVisitedRoute.and.returnValue(null);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.bn-card')).toBeNull();
  });

  it('should render suggestion when data is available', () => {
    mockTracker.getMostVisitedRoute.and.returnValue({
      route: '/alerts',
      count: 4,
      days: 5
    });
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.bn-card')).toBeTruthy();
    expect(compiled.querySelector('.bn-text')?.textContent).toContain('Alerts page');
    expect(compiled.querySelector('.bn-text')?.textContent).toContain('4 of the last 5 days');
  });

  it('should have correct routerLink for the suggestion', () => {
    mockTracker.getMostVisitedRoute.and.returnValue({
      route: '/health',
      count: 3,
      days: 3
    });
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('a[mat-flat-button]');
    expect(link.getAttribute('href')).toBe('/health');
  });
});
