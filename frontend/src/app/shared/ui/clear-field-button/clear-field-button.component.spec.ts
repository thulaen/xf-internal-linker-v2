import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ClearFieldButtonComponent } from './clear-field-button.component';
import { By } from '@angular/platform-browser';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

describe('ClearFieldButtonComponent', () => {
  let component: ClearFieldButtonComponent;
  let fixture: ComponentFixture<ClearFieldButtonComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ClearFieldButtonComponent, MatButtonModule, MatIconModule],
    }).compileComponents();

    fixture = TestBed.createComponent(ClearFieldButtonComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should not render button when show is false', () => {
    component.show = false;
    fixture.detectChanges();
    const button = fixture.debugElement.query(By.css('button'));
    expect(button).toBeNull();
  });

  it('should render button when show is true', () => {
    fixture.componentRef.setInput('show', true);
    fixture.detectChanges();
    const button = fixture.debugElement.query(By.css('button'));
    expect(button).toBeTruthy();
    expect(button.nativeElement.getAttribute('aria-label')).toBe('Clear field');
  });

  it('should use custom aria-label', () => {
    fixture.componentRef.setInput('show', true);
    fixture.componentRef.setInput('ariaLabel', 'Reset search');
    fixture.detectChanges();
    const button = fixture.debugElement.query(By.css('button'));
    expect(button).toBeTruthy();
    expect(button.nativeElement.getAttribute('aria-label')).toBe('Reset search');
  });

  it('should emit clear event and stop propagation when clicked', () => {
    fixture.componentRef.setInput('show', true);
    fixture.detectChanges();
    vi.spyOn(component.clear, 'emit').mockReturnValue(undefined as never);
    const button = fixture.debugElement.query(By.css('button'));
    expect(button).toBeTruthy();
    
    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true });
    vi.spyOn(clickEvent, 'stopPropagation').mockReturnValue(undefined as never);
    
    button.nativeElement.dispatchEvent(clickEvent);
    
    expect(component.clear.emit).toHaveBeenCalledWith(clickEvent);
    expect(clickEvent.stopPropagation).toHaveBeenCalled();
  });
});
