import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { CopyButtonComponent } from './copy-button.component';
import { ToastService } from '../../../core/services/toast.service';
import { By } from '@angular/platform-browser';
import { MatIconButton } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

describe('CopyButtonComponent', () => {
  let component: CopyButtonComponent;
  let fixture: ComponentFixture<CopyButtonComponent>;
  let mockToast: jasmine.SpyObj<ToastService>;
  let clipboardSpy: jasmine.Spy;

  beforeEach(async () => {
    mockToast = jasmine.createSpyObj('ToastService', ['show']);
    clipboardSpy = spyOn(navigator.clipboard, 'writeText');

    await TestBed.configureTestingModule({
      imports: [CopyButtonComponent, MatIconButton, MatIconModule, MatTooltipModule],
      providers: [
        { provide: ToastService, useValue: mockToast }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(CopyButtonComponent);
    component = fixture.componentInstance;
    component.value = 'Test content';
    fixture.detectChanges();
  });

  it('should render initial state', () => {
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent).toBe('content_copy');
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.getAttribute('aria-label')).toBe('Copy to clipboard');
  });

  it('should copy text and show success state', fakeAsync(() => {
    clipboardSpy.and.returnValue(Promise.resolve());
    
    component.copy();
    tick(); // Resolve clipboard promise
    fixture.detectChanges();
    
    expect(clipboardSpy).toHaveBeenCalledWith('Test content');
    expect(component.copied()).toBeTrue();
    
    const icon = fixture.debugElement.query(By.css('mat-icon'));
    expect(icon.nativeElement.textContent).toBe('check');
    expect(fixture.debugElement.query(By.css('.copy-btn-success'))).toBeTruthy();

    tick(2000); // Wait for the success state to revert
    fixture.detectChanges();
    
    expect(component.copied()).toBeFalse();
    expect(fixture.debugElement.query(By.css('.copy-btn-success'))).toBeNull();
    expect(fixture.debugElement.query(By.css('mat-icon')).nativeElement.textContent).toBe('content_copy');
  }));

  it('should show error toast on clipboard failure', fakeAsync(() => {
    clipboardSpy.and.returnValue(Promise.reject('error'));
    
    component.copy();
    tick(); // Resolve clipboard promise (failure path)
    
    expect(mockToast.show).toHaveBeenCalledWith('Could not copy to clipboard.', 'Dismiss', 4000);
    expect(component.copied()).toBeFalse();
  }));

  it('should use custom label and tooltip', () => {
    fixture.componentRef.setInput('label', 'Copy URL');
    fixture.componentRef.setInput('tooltip', 'Click to copy the direct link');
    fixture.detectChanges();
    
    const button = fixture.debugElement.query(By.css('button'));
    expect(button.nativeElement.getAttribute('aria-label')).toBe('Copy URL');
  });
});
