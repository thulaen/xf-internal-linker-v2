import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { signal } from '@angular/core';
import { DashboardModeTogglesComponent } from './dashboard-mode-toggles.component';
import { DashboardModesService } from '../../core/services/dashboard-modes.service';

describe('DashboardModeTogglesComponent', () => {
  // Writable signals so individual tests can flip state without re-creating the fixture.
  const safeSignal = signal(false);
  const calmSignal = signal(false);
  const toggleSafeSpy = vi.fn();
  const toggleCalmSpy = vi.fn();

  const mockModes = {
    safe: safeSignal,
    calm: calmSignal,
    toggleSafe: toggleSafeSpy,
    toggleCalm: toggleCalmSpy,
  };

  let fixture: ComponentFixture<DashboardModeTogglesComponent>;

  beforeEach(async () => {
    // Reset shared state so each test starts clean.
    safeSignal.set(false);
    calmSignal.set(false);
    toggleSafeSpy.mockClear();
    toggleCalmSpy.mockClear();

    await TestBed.configureTestingModule({
      imports: [DashboardModeTogglesComponent],
      providers: [
        provideNoopAnimations(),
        { provide: DashboardModesService, useValue: mockModes },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardModeTogglesComponent);
    fixture.detectChanges();
  });

  it('renders exactly two mode toggle buttons', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button');
    expect(buttons.length).toBe(2);
  });

  it('safe button shows lock_open icon when safe mode is off', () => {
    safeSignal.set(false);
    fixture.detectChanges();
    const icons = fixture.nativeElement.querySelectorAll('mat-icon');
    expect(icons[0].textContent.trim()).toBe('lock_open');
  });

  it('safe button shows lock icon when safe mode is on', () => {
    safeSignal.set(true);
    fixture.detectChanges();
    const icons = fixture.nativeElement.querySelectorAll('mat-icon');
    expect(icons[0].textContent.trim()).toBe('lock');
  });

  it('calls toggleSafe when first button is clicked', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button');
    buttons[0].click();
    expect(toggleSafeSpy).toHaveBeenCalledTimes(1);
    expect(toggleCalmSpy).not.toHaveBeenCalled();
  });

  it('calls toggleCalm when second button is clicked', () => {
    const buttons = fixture.nativeElement.querySelectorAll('button');
    buttons[1].click();
    expect(toggleCalmSpy).toHaveBeenCalledTimes(1);
    expect(toggleSafeSpy).not.toHaveBeenCalled();
  });

  it('calm button shows spa icon when calm mode is on', () => {
    calmSignal.set(true);
    fixture.detectChanges();
    const icons = fixture.nativeElement.querySelectorAll('mat-icon');
    expect(icons[1].textContent.trim()).toBe('spa');
  });
});
