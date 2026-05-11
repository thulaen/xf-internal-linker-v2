import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { ErrorCardComponent } from './error-card.component';

describe('ErrorCardComponent', () => {
  let component: ErrorCardComponent;
  let fixture: ComponentFixture<ErrorCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ErrorCardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(ErrorCardComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('heading', 'Could not load metrics');
    fixture.detectChanges();
  });

  it('renders the heading and default error tone', () => {
    const card = fixture.debugElement.query(By.css('.error-card'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(card.nativeElement.classList).toContain('tone-error');
    expect(card.nativeElement.getAttribute('role')).toBe('alert');
    expect(icon.nativeElement.textContent.trim()).toBe('error_outline');
    expect(fixture.nativeElement.textContent).toContain('Could not load metrics');
  });

  it('renders optional message and warning icon', () => {
    fixture.componentRef.setInput('message', 'The server did not respond.');
    fixture.componentRef.setInput('tone', 'warn');
    fixture.detectChanges();

    const card = fixture.debugElement.query(By.css('.error-card'));
    const icon = fixture.debugElement.query(By.css('mat-icon'));

    expect(card.nativeElement.classList).toContain('tone-warn');
    expect(icon.nativeElement.textContent.trim()).toBe('warning');
    expect(fixture.nativeElement.textContent).toContain('The server did not respond.');
  });

  it('emits retry when the retry button is clicked', () => {
    spyOn(component.retry, 'emit');

    const button = fixture.debugElement.query(By.css('button'));
    button.nativeElement.click();

    expect(component.retry.emit).toHaveBeenCalled();
  });

  it('hides the retry button when disabled', () => {
    fixture.componentRef.setInput('showRetry', false);
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('button'))).toBeNull();
  });
});
