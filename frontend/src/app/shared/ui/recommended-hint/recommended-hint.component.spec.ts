import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { RecommendedHintComponent } from './recommended-hint.component';

describe('RecommendedHintComponent', () => {
  let component: RecommendedHintComponent;
  let fixture: ComponentFixture<RecommendedHintComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RecommendedHintComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(RecommendedHintComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('recommended', '0.2');
    fixture.detectChanges();
  });

  it('renders the recommended value', () => {
    const pill = fixture.debugElement.query(By.css('.rh-pill'));

    expect(pill).toBeTruthy();
    expect(pill.nativeElement.textContent).toContain('Recommended: 0.2');
    expect(pill.nativeElement.classList).not.toContain('rh-match');
  });

  it('marks the hint as matched when current equals recommended', () => {
    fixture.componentRef.setInput('current', ' 0.2 ');
    fixture.detectChanges();

    const pill = fixture.debugElement.query(By.css('.rh-pill'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(component.matchesRecommended).toBe(true);
    expect(pill.nativeElement.classList).toContain('rh-match');
    expect(icon.nativeElement.textContent.trim()).toBe('check_circle');
  });

  it('renders why and impact hints when provided', () => {
    fixture.componentRef.setInput('why', 'Use this unless links look noisy.');
    fixture.componentRef.setInput('impactText', 'Affects review ranking.');
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.rh-why'))).toBeTruthy();
    expect(fixture.debugElement.query(By.css('.rh-impact'))).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Impacts downstream');
  });

  it('renders nothing when no recommended value is provided', () => {
    fixture.componentRef.setInput('recommended', null);
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.rh-pill'))).toBeNull();
  });
});
