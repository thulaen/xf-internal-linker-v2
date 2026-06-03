import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { GscSummaryCardComponent } from './gsc-summary-card.component';

/**
 * Host harness so we can exercise content projection (the body slot) and
 * the routed "Full report" link the way real callers use the card.
 */
@Component({
  standalone: true,
  imports: [GscSummaryCardComponent],
  template: `
    <app-gsc-summary-card
      [title]="title"
      [reportLink]="reportLink"
      [icon]="icon"
    >
      <p class="projected-body">body content</p>
    </app-gsc-summary-card>
  `,
})
class HostComponent {
  title = 'Performance';
  reportLink: string | null = '/analytics';
  icon = '';
}

describe('GscSummaryCardComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent, NoopAnimationsModule],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(host).toBeTruthy();
  });

  it('renders the title', () => {
    const titleEl = fixture.nativeElement.querySelector('.gsc-summary-card__title');
    expect(titleEl.textContent.trim()).toBe('Performance');
  });

  it('renders a "Full report" link to the provided route', () => {
    const link = fixture.nativeElement.querySelector('a.gsc-summary-card__report');
    expect(link).toBeTruthy();
    expect(link.getAttribute('href')).toContain('/analytics');
    expect(link.textContent).toContain('Full report');
  });

  it('projects body content into the card', () => {
    const projected = fixture.nativeElement.querySelector('.projected-body');
    expect(projected).toBeTruthy();
    expect(projected.textContent).toContain('body content');
  });

  it('hides the report link when reportLink is null', () => {
    host.reportLink = null;
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a.gsc-summary-card__report')).toBeNull();
  });

  it('shows an icon only when one is provided', () => {
    expect(fixture.nativeElement.querySelector('.gsc-summary-card__icon')).toBeNull();
    host.icon = 'insights';
    fixture.detectChanges();
    const icon = fixture.nativeElement.querySelector('.gsc-summary-card__icon');
    expect(icon).toBeTruthy();
    expect(icon.textContent.trim()).toBe('insights');
  });
});
