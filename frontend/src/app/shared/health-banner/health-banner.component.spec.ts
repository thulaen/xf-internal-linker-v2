import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

import { HealthBannerComponent } from './health-banner.component';

describe('HealthBannerComponent', () => {
  let fixture: ComponentFixture<HealthBannerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HealthBannerComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(HealthBannerComponent);
    fixture.componentRef.setInput('severity', 'info');
    fixture.componentRef.setInput('message', 'System is healthy');
    fixture.detectChanges();
  });

  it('renders the message and applies the correct severity class', () => {
    const banner = fixture.debugElement.query(By.css('.health-banner'));
    expect(banner.nativeElement.classList).toContain('severity-info');
    expect(banner.nativeElement.getAttribute('role')).toBe('alert');
    expect(fixture.nativeElement.textContent).toContain('System is healthy');
  });

  it('applies the severity-error class for error severity', () => {
    fixture.componentRef.setInput('severity', 'error');
    fixture.detectChanges();
    const banner = fixture.debugElement.query(By.css('.health-banner'));
    expect(banner.nativeElement.classList).toContain('severity-error');
  });

  it('renders the CTA link when both ctaLabel and ctaRoute are provided', () => {
    fixture.componentRef.setInput('ctaLabel', 'View details');
    fixture.componentRef.setInput('ctaRoute', '/health');
    fixture.detectChanges();
    const cta = fixture.debugElement.query(By.css('.banner-cta'));
    expect(cta).toBeTruthy();
    expect(cta.nativeElement.textContent.trim()).toBe('View details');
  });

  it('does not render a CTA link when ctaLabel is absent', () => {
    expect(fixture.debugElement.query(By.css('.banner-cta'))).toBeNull();
  });
});
