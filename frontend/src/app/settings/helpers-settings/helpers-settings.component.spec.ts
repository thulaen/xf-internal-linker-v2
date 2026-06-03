import { TestBed } from '@angular/core/testing';
import { EMPTY } from 'rxjs';

import { HelpersSettingsComponent } from './helpers-settings.component';
import { SiloSettingsService } from '../silo-settings.service';
import { MatSnackBar } from '@angular/material/snack-bar';

// Focused unit tests for the pure formatter helpers on the helper-nodes
// settings page. The component's heavy template + data load only run on
// detectChanges()/ngOnInit, which we deliberately do NOT call, so these stay
// fast and dependency-light. After the GPU-removal pass `formatCapabilities`
// must report CPU + RAM only and never mention graphics-card fields.
describe('HelpersSettingsComponent formatters', () => {
  let component: HelpersSettingsComponent;

  beforeEach(async () => {
    const siloStub = { listHelpers: () => EMPTY };
    const snackStub = { open: () => undefined };

    await TestBed.configureTestingModule({
      imports: [HelpersSettingsComponent],
      providers: [
        { provide: SiloSettingsService, useValue: siloStub },
        { provide: MatSnackBar, useValue: snackStub },
      ],
    }).compileComponents();

    component = TestBed.createComponent(HelpersSettingsComponent).componentInstance;
  });

  it('formatCapabilities reports CPU cores and RAM joined with a bullet', () => {
    expect(component.formatCapabilities({ cpu_cores: 8, ram_gb: 16 })).toBe('8 CPU cores • 16 GB RAM');
  });

  it('formatCapabilities returns "Not reported" for empty or missing capabilities', () => {
    expect(component.formatCapabilities(null)).toBe('Not reported');
    expect(component.formatCapabilities({})).toBe('Not reported');
  });

  it('formatCapabilities ignores leftover GPU capability keys', () => {
    const line = component.formatCapabilities({ cpu_cores: 4, ram_gb: 8, gpu_name: 'RTX 3050', gpu_vram_gb: 4 });
    expect(line).toBe('4 CPU cores • 8 GB RAM');
    expect(line).not.toContain('RTX');
    expect(line).not.toContain('VRAM');
  });

  it('formatList joins values or returns the empty label', () => {
    expect(component.formatList(['a', 'b'], 'none')).toBe('a • b');
    expect(component.formatList([], 'none')).toBe('none');
    expect(component.formatList(null, 'none')).toBe('none');
  });
});
