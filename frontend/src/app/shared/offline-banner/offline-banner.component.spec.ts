import { ComponentFixture, TestBed } from '@angular/core/testing';
import { OfflineBannerComponent } from './offline-banner.component';
import { By } from '@angular/platform-browser';

describe('OfflineBannerComponent', () => {
  let component: OfflineBannerComponent;
  let fixture: ComponentFixture<OfflineBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [OfflineBannerComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(OfflineBannerComponent);
    component = fixture.componentInstance;
  });

  it('should be hidden when online', () => {
    // navigator.onLine is usually true in tests, but we force an online event to be sure
    window.dispatchEvent(new Event('online'));
    fixture.detectChanges();
    const banner = fixture.debugElement.query(By.css('.offline-banner'));
    expect(banner).toBeNull();
  });

  it('should show when offline event fires', () => {
    window.dispatchEvent(new Event('offline'));
    fixture.detectChanges();
    
    expect(component.online()).toBe(false);
    const banner = fixture.debugElement.query(By.css('.offline-banner'));
    expect(banner).toBeTruthy();
    expect(banner.nativeElement.textContent).toContain("You're offline");
  });

  it('should hide when online event fires after being offline', () => {
    window.dispatchEvent(new Event('offline'));
    fixture.detectChanges();
    expect(component.online()).toBe(false);

    window.dispatchEvent(new Event('online'));
    fixture.detectChanges();
    
    expect(component.online()).toBe(true);
    const banner = fixture.debugElement.query(By.css('.offline-banner'));
    expect(banner).toBeNull();
  });
});
