import { TestBed } from '@angular/core/testing';
import { EMPTY } from 'rxjs';

import { PerformanceSettingsComponent } from './performance-settings.component';
import { SiloSettingsService } from '../silo-settings.service';
import { MatSnackBar } from '@angular/material/snack-bar';

// Focused unit tests for the performance-settings TS class. ngOnInit kicks off
// runtime loads, so we deliberately skip detectChanges() and exercise the pure
// logic only. After the GPU-removal pass the default registration form must
// target the CPU and a paid-API model family — never a CUDA device.
describe('PerformanceSettingsComponent', () => {
  let component: PerformanceSettingsComponent;

  beforeEach(async () => {
    const siloStub = {
      getRuntimeConfig: () => EMPTY,
      getRuntimeSummary: () => EMPTY,
      listHelpers: () => EMPTY,
    };
    const snackStub = { open: () => undefined };

    await TestBed.configureTestingModule({
      imports: [PerformanceSettingsComponent],
      providers: [
        { provide: SiloSettingsService, useValue: siloStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    }).compileComponents();

    component = TestBed.createComponent(PerformanceSettingsComponent).componentInstance;
  });

  it('defaults the registration form to CPU + paid-API (no GPU device)', () => {
    expect(component.registration.device_target).toBe('cpu');
    expect(component.registration.model_family).toBe('paid-api');
    expect(component.registration.device_target).not.toBe('cuda');
  });

  it('humanBytes formats sizes and guards against bad input', () => {
    expect(component.humanBytes(0)).toBe('0 B');
    expect(component.humanBytes(null)).toBe('0 B');
    expect(component.humanBytes(512)).toBe('512 B');
    expect(component.humanBytes(1024)).toBe('1.0 KB');
    expect(component.humanBytes(1024 * 1024)).toBe('1.0 MB');
    expect(component.humanBytes(15 * 1024)).toBe('15 KB');
  });

  it('reset restores the captured initial CPU + queue values', () => {
    component.batchSize.set(99);
    component.cpuEncodeThreads.set(9);
    component.defaultQueueConcurrency.set(6);
    component.aggressiveOomBackoff.set(false);

    component.reset();

    expect(component.batchSize()).toBe(32);
    expect(component.cpuEncodeThreads()).toBe(4);
    expect(component.defaultQueueConcurrency()).toBe(2);
    expect(component.aggressiveOomBackoff()).toBe(true);
  });
});
