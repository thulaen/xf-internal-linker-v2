import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LoadingButtonComponent } from './loading-button.component';
import { By } from '@angular/platform-browser';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

describe('LoadingButtonComponent', () => {
  let component: LoadingButtonComponent;
  let fixture: ComponentFixture<LoadingButtonComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoadingButtonComponent, MatButtonModule, MatProgressSpinnerModule],
    }).compileComponents();

    fixture = TestBed.createComponent(LoadingButtonComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should render initial state as primary flat button', () => {
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.classList).toContain('mat-mdc-unelevated-button'); // mat-flat-button
    expect(button.nativeElement.getAttribute('disabled')).toBeNull();
    expect(fixture.debugElement.query(By.css('mat-spinner'))).toBeNull();
  });

  it('should show loading state', () => {
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.getAttribute('disabled')).toBe('true');
    expect(button.nativeElement.getAttribute('aria-busy')).toBe('true');
    
    const spinner = fixture.debugElement.query(By.css('mat-spinner'));
    expect(spinner).toBeTruthy();
    expect(spinner.nativeElement.getAttribute('aria-label')).toBe('Loading');
    
    const label = fixture.debugElement.query(By.css('.btn-label'));
    expect(label.nativeElement.classList).toContain('btn-label-loading');
  });

  it('should respect disabled input', () => {
    fixture.componentRef.setInput('disabled', true);
    fixture.detectChanges();
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.getAttribute('disabled')).toBe('true');
  });

  it('should change variants', () => {
    fixture.componentRef.setInput('variant', 'stroked');
    fixture.detectChanges();
    let button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.classList).toContain('mat-mdc-outlined-button');

    fixture.componentRef.setInput('variant', 'basic');
    fixture.detectChanges();
    button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.classList).toContain('mat-mdc-button');
  });

  it('should emit clicked event when not loading/disabled', () => {
    vi.spyOn(component.clicked, 'emit').mockReturnValue(undefined as never);
    const button = fixture.debugElement.query(By.css('button'));
    button.nativeElement.click();
    expect(component.clicked.emit).toHaveBeenCalled();
  });

  it('should not emit clicked event when loading', () => {
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    vi.spyOn(component.clicked, 'emit').mockReturnValue(undefined as never);
    const button = fixture.debugElement.query(By.css('button'));
    button.nativeElement.click();
    expect(component.clicked.emit).not.toHaveBeenCalled();
  });
});
