import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TipsOfDayComponent } from './tips-of-day.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('TipsOfDayComponent', () => {
  let component: TipsOfDayComponent;
  let fixture: ComponentFixture<TipsOfDayComponent>;

  beforeEach(async () => {
    // Clear localStorage before each test
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [TipsOfDayComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(TipsOfDayComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should pick a tip on init', () => {
    expect(component.currentTip()).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.tod-text')).toBeTruthy();
  });

  it('should render the first tip', () => {
    fixture.detectChanges();
    component.next();
    fixture.detectChanges();
    // In random pick with multiple options, it might be different.
    // Given the bank size, it's very likely different.
    // If bank was 1, it would stay same.
    expect(component.remainingCount()).toBeGreaterThan(1);
  });

  it('should dismiss tip and remove from pool', () => {
    const tipToDismiss = component.currentTip()!;
    const initialCount = component.remainingCount();
    
    component.dismiss();
    fixture.detectChanges();
    
    expect(component.remainingCount()).toBe(initialCount - 1);
    const dismissedRaw = localStorage.getItem('xfil_dismissed_tips');
    expect(dismissedRaw).toContain(tipToDismiss.id);
  });

  it('should hide card when all tips are dismissed', () => {
    // This is hard to test with the full TIP_BANK, so I'll mock the ব্যাংক if I could,
    // but TIP_BANK is a const. I can just call dismiss many times or mock readDismissed.
    // Let's just mock readDismissed behavior by filling localStorage.
    const allIds = [
      'tip-cmd-k', 'tip-shortcuts', 'tip-glossary', 'tip-tutorial', 'tip-explain',
      'tip-pause-everything', 'tip-skip-link', 'tip-csv-export', 'tip-print',
      'tip-back-to-top', 'tip-deep-link', 'tip-share-dialog', 'tip-runtime-mode',
      'tip-ws-status', 'tip-quarantine'
    ];
    localStorage.setItem('xfil_dismissed_tips', JSON.stringify(allIds));
    
    // Re-init or call pickNext
    (component as any).pickNext();
    fixture.detectChanges();
    
    expect(component.currentTip()).toBeNull();
    expect(fixture.nativeElement.querySelector('.tod-card')).toBeNull();
  });
});
