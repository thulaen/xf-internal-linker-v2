import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { FreshnessBadgeComponent } from './freshness-badge.component';

describe('FreshnessBadgeComponent', () => {
  let fixture: ComponentFixture<FreshnessBadgeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FreshnessBadgeComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(FreshnessBadgeComponent);
    fixture.detectChanges();
  });

  it('renders "Never synced" with expired class when updatedAt is null', () => {
    const chip = fixture.debugElement.query(By.css('mat-chip'));
    expect(chip.nativeElement.classList).toContain('freshness-expired');
    expect(fixture.nativeElement.textContent).toContain('Never synced');
  });

  it('renders fresh class when updatedAt is within the stale window', () => {
    const thirtyMinutesAgo = new Date(Date.now() - 30 * 60_000).toISOString();
    fixture.componentRef.setInput('updatedAt', thirtyMinutesAgo);
    fixture.componentRef.setInput('staleAfterHours', 24);
    fixture.detectChanges();
    const chip = fixture.debugElement.query(By.css('mat-chip'));
    expect(chip.nativeElement.classList).toContain('freshness-fresh');
  });

  it('renders stale class when updatedAt is between 1× and 3× staleAfterHours', () => {
    // 2 hours ago with a 1-hour threshold → hoursAgo(2) > 1 and <= 3 → stale
    const twoHoursAgo = new Date(Date.now() - 2 * 3_600_000).toISOString();
    fixture.componentRef.setInput('updatedAt', twoHoursAgo);
    fixture.componentRef.setInput('staleAfterHours', 1);
    fixture.detectChanges();
    const chip = fixture.debugElement.query(By.css('mat-chip'));
    expect(chip.nativeElement.classList).toContain('freshness-stale');
  });

  it('shows the check_circle icon when data is fresh', () => {
    const fiveSecondsAgo = new Date(Date.now() - 5_000).toISOString();
    fixture.componentRef.setInput('updatedAt', fiveSecondsAgo);
    fixture.detectChanges();
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent.trim()).toBe('check_circle');
  });
});
