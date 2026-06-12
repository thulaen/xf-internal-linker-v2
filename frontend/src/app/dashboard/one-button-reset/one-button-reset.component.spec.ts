import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { OneButtonResetComponent } from './one-button-reset.component';
import { DashboardService } from '../dashboard.service';
import { RealtimeService } from '../../core/services/realtime.service';
import { MatSnackBar } from '@angular/material/snack-bar';

describe('OneButtonResetComponent', () => {
  let component: OneButtonResetComponent;
  let fixture: ComponentFixture<OneButtonResetComponent>;
  let mockDash: Partial<DashboardService>;
  let mockRealtime: Partial<RealtimeService>;
  let mockSnack: Partial<MatSnackBar>;

  beforeEach(async () => {
    mockDash = {
      invalidate: vi.fn(),
      refresh: vi.fn().mockReturnValue(of(null))
    };
    mockRealtime = {
      reconnectNow: vi.fn()
    };
    mockSnack = {
      open: vi.fn()
    };

    await TestBed.configureTestingModule({
      imports: [OneButtonResetComponent],
      providers: [
        { provide: DashboardService, useValue: mockDash },
        { provide: RealtimeService, useValue: mockRealtime },
        { provide: MatSnackBar, useValue: mockSnack }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(OneButtonResetComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should call invalidate and refresh on reset', () => {
    component.onReset();
    expect(mockDash.invalidate).toHaveBeenCalled();
    expect(mockDash.refresh).toHaveBeenCalled();
    expect(mockRealtime.reconnectNow).toHaveBeenCalled();
    expect(mockSnack.open).toHaveBeenCalledWith('Dashboard view reset.', 'OK', expect.any(Object));
  });

  it('should handle refresh error', () => {
    (mockDash.refresh as unknown as Spy).mockReturnValue(throwError(() => new Error('fail')));
    component.onReset();
    expect(component.busy()).toBe(false);
    expect(mockSnack.open).toHaveBeenCalledWith('Reset failed — check your connection.', 'Dismiss', expect.any(Object));
  });

  it('should show last reset label', () => {
    const now = Date.now();
    component.lastResetAt.set(now - 5000); // 5s ago
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.obr-meta')?.textContent).toContain('Last reset 5s ago');
  });
});
