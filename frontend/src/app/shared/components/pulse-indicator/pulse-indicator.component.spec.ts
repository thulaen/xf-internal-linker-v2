import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PulseIndicatorComponent } from './pulse-indicator.component';
import { By } from '@angular/platform-browser';

describe('PulseIndicatorComponent', () => {
  let component: PulseIndicatorComponent;
  let fixture: ComponentFixture<PulseIndicatorComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PulseIndicatorComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(PulseIndicatorComponent);
    component = fixture.componentInstance;
  });

  it('should have active class when active is true', () => {
    component.active = true;
    fixture.detectChanges();
    const dot = fixture.debugElement.query(By.css('.pulse-dot'));
    expect(dot.nativeElement.classList).toContain('active');
  });

  it('should not have active class when active is false', () => {
    component.active = false;
    fixture.detectChanges();
    const dot = fixture.debugElement.query(By.css('.pulse-dot'));
    expect(dot.nativeElement.classList).not.toContain('active');
  });

  it('should set aria-label correctly', () => {
    component.ariaLabel = 'System online';
    fixture.detectChanges();
    const dot = fixture.debugElement.query(By.css('.pulse-dot'));
    expect(dot.nativeElement.getAttribute('aria-label')).toBe('System online');
  });
});
