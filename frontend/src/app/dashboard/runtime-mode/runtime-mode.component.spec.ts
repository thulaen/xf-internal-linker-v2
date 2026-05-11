import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RuntimeModeComponent } from './runtime-mode.component';
import { provideRouter } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('RuntimeModeComponent', () => {
  let component: RuntimeModeComponent;
  let fixture: ComponentFixture<RuntimeModeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RuntimeModeComponent, NoopAnimationsModule],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(RuntimeModeComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display CPU Mode by default', () => {
    const chip = fixture.nativeElement.querySelector('.mode-chip');
    expect(chip.textContent).toContain('CPU Mode');
    expect(chip.classList).toContain('mode-cpu');
  });

  it('should display GPU Active when mode is gpu', () => {
    fixture.componentRef.setInput('mode', 'gpu');
    fixture.detectChanges();
    const chip = fixture.nativeElement.querySelector('.mode-chip');
    expect(chip.textContent).toContain('GPU Active');
    expect(chip.classList).toContain('mode-gpu');
  });

  it('should display warming hint when mode is warming', () => {
    fixture.componentRef.setInput('mode', 'warming');
    fixture.detectChanges();
    const chip = fixture.nativeElement.querySelector('.mode-chip');
    expect(chip.textContent).toContain('GPU Warming Up');
    expect(chip.classList).toContain('mode-warming');
    const hint = fixture.nativeElement.querySelector('.warming-hint');
    expect(hint).toBeTruthy();
    expect(hint.textContent).toContain('GPU is warming up');
  });

  it('should have a link to performance mode', () => {
    const btn = fixture.nativeElement.querySelector('.runtime-adjust-btn');
    expect(btn).toBeTruthy();
    expect(btn.getAttribute('href')).toBe('/dashboard#performance-mode');
  });
});
