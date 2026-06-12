import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WelcomeCardComponent } from './welcome-card.component';
import { GuidedTourService, DASHBOARD_TOUR } from '../../core/services/guided-tour.service';
import { By } from '@angular/platform-browser';

describe('WelcomeCardComponent', () => {
  let component: WelcomeCardComponent;
  let fixture: ComponentFixture<WelcomeCardComponent>;
  let tourServiceSpy: SpyObj<GuidedTourService>;

  beforeEach(async () => {
    tourServiceSpy = createSpyObj(['start']);
    
    // Clear localStorage before each test
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [WelcomeCardComponent],
      providers: [
        { provide: GuidedTourService, useValue: tourServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(WelcomeCardComponent);
    component = fixture.componentInstance;
  });

  it('should be visible if not seen before', () => {
    fixture.detectChanges();
    expect(component.visible()).toBe(true);
    const card = fixture.debugElement.query(By.css('.wc-card'));
    expect(card).toBeTruthy();
  });

  it('should be hidden if already seen', () => {
    localStorage.setItem('xfil_welcome_card_seen', '1');
    component.ngOnInit();
    fixture.detectChanges();
    expect(component.visible()).toBe(false);
    const card = fixture.debugElement.query(By.css('.wc-card'));
    expect(card).toBeNull();
  });

  it('should dismiss and hide when "Skip for now" is clicked', () => {
    fixture.detectChanges();
    // Use explicit button index or text since they are mat-buttons
    const buttons = fixture.debugElement.queryAll(By.css('button'));
    const skipBtn = buttons.find(b => b.nativeElement.textContent.includes('Skip for now'));
    expect(skipBtn).toBeTruthy();
    skipBtn!.nativeElement.click();
    fixture.detectChanges();
    
    expect(component.visible()).toBe(false);
    expect(localStorage.getItem('xfil_welcome_card_seen')).toBe('1');
  });

  it('should start tour and dismiss when "Take the tour" is clicked', () => {
    fixture.detectChanges();
    const buttons = fixture.debugElement.queryAll(By.css('button'));
    const tourBtn = buttons.find(b => b.nativeElement.textContent.includes('Take the tour'));
    expect(tourBtn).toBeTruthy();
    tourBtn!.nativeElement.click();
    fixture.detectChanges();

    expect(tourServiceSpy.start).toHaveBeenCalledWith(DASHBOARD_TOUR);
    expect(component.visible()).toBe(false);
    expect(localStorage.getItem('xfil_welcome_card_seen')).toBe('1');
  });
});
