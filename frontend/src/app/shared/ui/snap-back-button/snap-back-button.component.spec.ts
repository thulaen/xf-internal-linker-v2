import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { SnapBackButtonComponent } from './snap-back-button.component';

describe('SnapBackButtonComponent', () => {
  let component: SnapBackButtonComponent;
  let fixture: ComponentFixture<SnapBackButtonComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SnapBackButtonComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(SnapBackButtonComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('current', 'custom');
    fixture.componentRef.setInput('defaultValue', 'default');
    fixture.detectChanges();
  });

  it('enables the button when the current value differs from the default', () => {
    const button = fixture.debugElement.query(By.css('button'));

    expect(component.matches).toBeFalse();
    expect(button.nativeElement.disabled).toBeFalse();
    expect(button.nativeElement.getAttribute('aria-label')).toBe('Reset to default default');
  });

  it('disables the button when the current value matches the default', () => {
    fixture.componentRef.setInput('current', ' default ');
    fixture.detectChanges();

    const button = fixture.debugElement.query(By.css('button'));

    expect(component.matches).toBeTrue();
    expect(button.nativeElement.disabled).toBeTrue();
  });

  it('emits the default value when clicked', () => {
    spyOn(component.snap, 'emit');

    const button = fixture.debugElement.query(By.css('button'));
    button.nativeElement.click();

    expect(component.snap.emit).toHaveBeenCalledWith('default');
  });
});
