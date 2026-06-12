import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { RateLimitSnackbarComponent, RateLimitSnackbarData } from './rate-limit-snackbar.component';
import { MatSnackBarRef, MAT_SNACK_BAR_DATA } from '@angular/material/snack-bar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

describe('RateLimitSnackbarComponent', () => {
  let component: RateLimitSnackbarComponent;
  let fixture: ComponentFixture<RateLimitSnackbarComponent>;
  let mockSnackRef: SpyObj<MatSnackBarRef<RateLimitSnackbarComponent>>;
  let mockData: RateLimitSnackbarData;

  beforeEach(async () => {
    mockSnackRef = createSpyObj(['dismiss']);
    mockData = { seconds: 5 };

    await TestBed.configureTestingModule({
      imports: [RateLimitSnackbarComponent, MatIconModule, MatButtonModule],
      providers: [
        { provide: MatSnackBarRef, useValue: mockSnackRef },
        { provide: MAT_SNACK_BAR_DATA, useValue: mockData }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(RateLimitSnackbarComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with provided seconds', () => {
    fixture.detectChanges();
    expect(component.remainingSeconds).toBe(5);
    expect(component.remainingLabel).toBe('5 seconds');
  });

  it('should dismiss immediately if seconds <= 0', () => {
    component.remainingSeconds = 0;
    component.ngOnInit();
    expect(mockSnackRef.dismiss).toHaveBeenCalled();
  });

  it('should countdown every second', fakeAsync(() => {
    fixture.detectChanges();
    expect(component.remainingSeconds).toBe(5);

    tick(1000);
    expect(component.remainingSeconds).toBe(4);
    expect(component.remainingLabel).toBe('4 seconds');

    tick(3000);
    expect(component.remainingSeconds).toBe(1);
    expect(component.remainingLabel).toBe('1 second');

    tick(1000);
    expect(component.remainingSeconds).toBe(0);
    expect(mockSnackRef.dismiss).toHaveBeenCalled();
  }));

  it('should format minutes correctly', () => {
    component.remainingSeconds = 65;
    expect(component.remainingLabel).toBe('1m 05s');

    component.remainingSeconds = 120;
    expect(component.remainingLabel).toBe('2 minutes');
  });

  it('should dismiss when Dismiss button is clicked', () => {
    fixture.detectChanges();
    const btn = fixture.nativeElement.querySelector('.rl-dismiss');
    btn.click();
    expect(mockSnackRef.dismiss).toHaveBeenCalled();
  });
});
