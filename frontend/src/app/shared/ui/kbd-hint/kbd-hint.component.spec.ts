import { ComponentFixture, TestBed } from '@angular/core/testing';
import { KbdHintComponent } from './kbd-hint.component';
import { By } from '@angular/platform-browser';
import { A11yPrefsService } from '../../../core/services/a11y-prefs.service';

describe('KbdHintComponent', () => {
  let fixture: ComponentFixture<KbdHintComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [KbdHintComponent],
      providers: [
        { provide: A11yPrefsService, useValue: {} }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(KbdHintComponent);
    fixture.detectChanges();
  });

  it('should render empty when no keys provided', () => {
    fixture.componentRef.setInput('keys', '');
    fixture.detectChanges();
    const hints = fixture.debugElement.queryAll(By.css('.kbd-hint'));
    expect(hints.length).toBe(0);
  });

  it('should split and render keys', () => {
    fixture.componentRef.setInput('keys', 'Ctrl+S');
    fixture.detectChanges();
    const hints = fixture.debugElement.queryAll(By.css('.kbd-hint'));
    expect(hints.length).toBe(2);
    // On non-Mac (default in many test envs unless mocked), it should be Ctrl and S
    // We check content to see what normalize did.
    const texts = hints.map(h => h.nativeElement.textContent.trim());
    expect(texts).toContain('Ctrl');
    expect(texts).toContain('S');
  });

  it('should pick only first alternate if comma separated', () => {
    fixture.componentRef.setInput('keys', 'Ctrl+S, Shift+S');
    fixture.detectChanges();
    const hints = fixture.debugElement.queryAll(By.css('.kbd-hint'));
    expect(hints.length).toBe(2); // Only Ctrl and S
    const texts = hints.map(h => h.nativeElement.textContent.trim());
    expect(texts).toContain('Ctrl');
    expect(texts).toContain('S');
    expect(texts).not.toContain('Shift');
  });

  it('should handle single keys', () => {
    fixture.componentRef.setInput('keys', 'G');
    fixture.detectChanges();
    const hints = fixture.debugElement.queryAll(By.css('.kbd-hint'));
    expect(hints.length).toBe(1);
    expect(hints[0].nativeElement.textContent.trim()).toBe('G');
  });

  // Testing the private normalize method directly or via property if it were public
  // Since it relies on navigator.platform, we can't easily switch it in unit tests 
  // without complex mocking of global navigator, but we can verify it doesn't crash.
});
