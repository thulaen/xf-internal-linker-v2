import { ComponentFixture, TestBed } from '@angular/core/testing';
import { PerformanceModeComponent, ConfirmHighPerformanceDialogComponent } from './performance-mode.component';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PerformanceModeService } from '../../core/services/performance-mode.service';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { signal } from '@angular/core';

describe('PerformanceModeComponent', () => {
  let component: PerformanceModeComponent;
  let fixture: ComponentFixture<PerformanceModeComponent>;
  let httpMock: HttpTestingController;
  let perfModeService: jasmine.SpyObj<PerformanceModeService>;

  beforeEach(async () => {
    const perfModeSpy = jasmine.createSpyObj('PerformanceModeService', ['refresh', 'setExpiry'], {
      expiry: signal('none'),
      highPerformanceCapable: signal(true),
      hardwareTier: signal('high'),
      hardwareSummary: signal('RTX 3050 6GB'),
    });
    perfModeSpy.refresh.and.returnValue(of(null));

    await TestBed.configureTestingModule({
      imports: [
        HttpClientTestingModule,
        MatSnackBarModule,
        MatDialogModule,
        NoopAnimationsModule,
        PerformanceModeComponent
      ],
      providers: [
        { provide: PerformanceModeService, useValue: perfModeSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PerformanceModeComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    perfModeService = TestBed.inject(PerformanceModeService) as jasmine.SpyObj<PerformanceModeService>;
    fixture.detectChanges();

    // Initial ngOnInit call
    const req = httpMock.expectOne('/api/system/safe-mode-boot/');
    req.flush({ armed: false });
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should reflect hardware capability from service', () => {
    expect(component.highCapable()).toBeTrue();
    const highButton = fixture.nativeElement.querySelector('.mode-button:nth-child(3)');
    expect(highButton.disabled).toBeFalse();
  });

  it('should disable high performance button if not capable', () => {
    (perfModeService as any).highPerformanceCapable.set(false);
    fixture.detectChanges();
    const highButton = fixture.nativeElement.querySelector('.mode-button:nth-child(3)');
    expect(highButton.disabled).toBeTrue();
    expect(highButton.classList).toContain('unavailable');
  });

  it('should switch mode when button is clicked (except high)', () => {
    component.currentMode = 'balanced';
    const safeButton = fixture.nativeElement.querySelector('.mode-button:nth-child(1)');
    safeButton.click();
    
    const req = httpMock.expectOne('/api/settings/runtime/switch/');
    expect(req.request.body).toEqual({ mode: 'safe' });
    req.flush({});
    
    expect(component.currentMode).toBe('safe');
  });

  it('should open confirmation dialog when switching to high performance', () => {
    const dialog = TestBed.inject(MatDialog);
    spyOn(dialog, 'open').and.returnValue({
      afterClosed: () => of(true)
    } as any);

    const highButton = fixture.nativeElement.querySelector('.mode-button:nth-child(3)');
    highButton.click();

    expect(dialog.open).toHaveBeenCalledWith(ConfirmHighPerformanceDialogComponent, jasmine.any(Object));
    
    const req = httpMock.expectOne('/api/settings/runtime/switch/');
    req.flush({});
    expect(component.currentMode).toBe('high');
  });

  it('should arm safe mode boot', () => {
    const safeBootButton = fixture.nativeElement.querySelector('button[mat-stroked-button]');
    safeBootButton.click();

    const req = httpMock.expectOne('/api/system/safe-mode-boot/');
    expect(req.request.method).toBe('POST');
    req.flush({ armed: true });

    expect(component.bootArmed()).toBeTrue();
  });
});
