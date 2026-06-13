import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { EmergencyStopComponent } from './emergency-stop.component';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';

describe('EmergencyStopComponent', () => {
  let fixture: ComponentFixture<EmergencyStopComponent>;
  let component: EmergencyStopComponent;
  let confirmSpy: SpyObj<ConfirmService>;
  let snackSpy: SpyObj<MatSnackBar>;

  beforeEach(async () => {
    confirmSpy = createSpyObj(['ask']);
    // Default: user cancels the first confirm dialog.
    confirmSpy.ask.mockReturnValue(Promise.resolve(false));

    snackSpy = createSpyObj(['open']);

    await TestBed.configureTestingModule({
      imports: [EmergencyStopComponent],
      providers: [
        provideNoopAnimations(),
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        { provide: ConfirmService, useValue: confirmSpy },
        { provide: MatSnackBar, useValue: snackSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(EmergencyStopComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the emergency stop button', () => {
    const btn = fixture.nativeElement.querySelector('.es-btn');
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('Emergency stop');
  });

  it('is not busy on initialisation', () => {
    expect(component.busy()).toBe(false);
  });

  it('button is enabled when not busy', () => {
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('.es-btn');
    expect(btn.disabled).toBe(false);
  });

  it('opens the confirm dialog when the button is clicked', async () => {
    fixture.nativeElement.querySelector('.es-btn').click();
    await fixture.whenStable();
    expect(confirmSpy.ask).toHaveBeenCalledTimes(1);
    expect(confirmSpy.ask).toHaveBeenCalledWith(expect.objectContaining({ title: expect.any(String), danger: true }));
  });

  it('stays not busy when the confirm dialog is cancelled', async () => {
    confirmSpy.ask.mockReturnValue(Promise.resolve(false));
    fixture.nativeElement.querySelector('.es-btn').click();
    await fixture.whenStable();
    expect(component.busy()).toBe(false);
  });

  it('does not make HTTP calls when confirm dialog is cancelled', async () => {
    const httpMock = TestBed.inject(HttpTestingController);
    confirmSpy.ask.mockReturnValue(Promise.resolve(false));
    fixture.nativeElement.querySelector('.es-btn').click();
    await fixture.whenStable();
    // Verify no requests were made to master-pause.
    httpMock.expectNone('/api/settings/master-pause/');
    expect(confirmSpy.ask).toHaveBeenCalledTimes(1);
    httpMock.verify();
  });
});
