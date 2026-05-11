import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BaselineIndicatorComponent } from './baseline-indicator.component';
import { By } from '@angular/platform-browser';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

describe('BaselineIndicatorComponent', () => {
  let fixture: ComponentFixture<BaselineIndicatorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [BaselineIndicatorComponent, MatIconModule, MatTooltipModule],
    }).compileComponents();

    fixture = TestBed.createComponent(BaselineIndicatorComponent);
  });

  it('should render neutral state when within noise', () => {
    fixture.componentRef.setInput('current', 105);
    fixture.componentRef.setInput('baseline', [100, 110, 95, 105, 90, 115, 100]); // Mean 102.1, StdDev 8.5
    fixture.detectChanges();
    
    const chip = fixture.debugElement.query(By.css('.bi-chip'));
    expect(chip.nativeElement.textContent).toContain('within noise');
    expect(chip.nativeElement.classList.contains('bi-good')).toBeFalse();
    expect(chip.nativeElement.classList.contains('bi-bad')).toBeFalse();
    
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent).toBe('check_circle');
  });

  it('should show good state when significantly above baseline and goodDirection is up', () => {
    fixture.componentRef.setInput('current', 150);
    fixture.componentRef.setInput('baseline', [100, 105, 95, 100, 110]); // Mean 102, StdDev 5.7. Z = (150-102)/5.7 = 8.4
    fixture.componentRef.setInput('goodDirection', 'up');
    fixture.detectChanges();
    
    const chip = fixture.debugElement.query(By.css('.bi-chip'));
    expect(chip.nativeElement.textContent).toContain('8.4σ above baseline');
    expect(chip.nativeElement.classList).toContain('bi-good');
    
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent).toBe('north');
  });

  it('should show bad state when significantly below baseline and goodDirection is up', () => {
    fixture.componentRef.setInput('current', 50);
    fixture.componentRef.setInput('baseline', [100, 105, 95, 100, 110]); // Mean 102, StdDev 5.7. Z = (50-102)/5.7 = -9.1
    fixture.componentRef.setInput('goodDirection', 'up');
    fixture.detectChanges();
    
    const chip = fixture.debugElement.query(By.css('.bi-chip'));
    expect(chip.nativeElement.textContent).toContain('9.1σ below baseline');
    expect(chip.nativeElement.classList).toContain('bi-bad');
    
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent).toBe('south');
  });
});
