import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WhatsNewComponent } from './whats-new.component';
import { provideRouter } from '@angular/router';
import { By } from '@angular/platform-browser';

describe('WhatsNewComponent', () => {
  let component: WhatsNewComponent;
  let fixture: ComponentFixture<WhatsNewComponent>;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [WhatsNewComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(WhatsNewComponent);
    component = fixture.componentInstance;
  });

  it('should show top 2 entries for first-time visitor (no cutoff)', () => {
    fixture.detectChanges();
    // Assuming CHANGELOG has at least 2 entries as seen in whats-new.data.ts
    expect(component.entries().length).toBe(2);
    const items = fixture.debugElement.queryAll(By.css('.wn-item'));
    expect(items.length).toBe(2);
  });

  it('should show entries newer than cutoff', () => {
    // 2026-04-16 is newest-1. 2026-04-17 is newest.
    // If we set cutoff to 2026-04-16T00:00:00Z, we should only see 2026-04-17T00:00:00Z.
    localStorage.setItem('xfil_changelog_seen_iso', '2026-04-16T00:00:00Z');
    component.ngOnInit();
    fixture.detectChanges();
    
    expect(component.entries().length).toBe(1);
    expect(component.entries()[0].title).toContain('Phase D3');
  });

  it('should hide card when everything is seen', () => {
    localStorage.setItem('xfil_changelog_seen_iso', '2026-04-17T00:00:00Z');
    component.ngOnInit();
    fixture.detectChanges();
    
    expect(component.entries().length).toBe(0);
    const card = fixture.debugElement.query(By.css('.wn-card'));
    expect(card).toBeNull();
  });

  it('should mark as read and hide card', () => {
    fixture.detectChanges();
    expect(component.entries().length).toBeGreaterThan(0);
    
    const buttons = fixture.debugElement.queryAll(By.css('button'));
    const markReadBtn = buttons.find(b => b.nativeElement.textContent.includes('Mark as read'));
    expect(markReadBtn).toBeTruthy();
    markReadBtn!.nativeElement.click();
    fixture.detectChanges();
    
    expect(component.entries().length).toBe(0);
    const card = fixture.debugElement.query(By.css('.wn-card'));
    expect(card).toBeNull();
    // Check that the newest date was stored
    expect(localStorage.getItem('xfil_changelog_seen_iso')).toBe('2026-04-17T00:00:00Z');
  });
});
