import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { ConfidenceBadgeComponent } from './confidence-badge.component';

describe('ConfidenceBadgeComponent', () => {
  let fixture: ComponentFixture<ConfidenceBadgeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfidenceBadgeComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ConfidenceBadgeComponent);
    fixture.componentRef.setInput('level', 'high');
    fixture.detectChanges();
  });

  it('renders with the correct chip class for the level', () => {
    const chip = fixture.debugElement.query(By.css('mat-chip'));
    expect(chip.nativeElement.classList).toContain('confidence-high');
  });

  it('shows the default label for the given level', () => {
    expect(fixture.nativeElement.textContent.trim()).toBe('High confidence');
  });

  it('overrides the label when a custom label is supplied', () => {
    fixture.componentRef.setInput('label', 'Very strong signal');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent.trim()).toBe('Very strong signal');
  });

  it('applies the thin class and shows the thin-data label', () => {
    fixture.componentRef.setInput('level', 'thin');
    fixture.detectChanges();
    const chip = fixture.debugElement.query(By.css('mat-chip'));
    expect(chip.nativeElement.classList).toContain('confidence-thin');
    expect(fixture.nativeElement.textContent.trim()).toBe('Insufficient data');
  });
});
