import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { SpikeInsightCardComponent } from './spike-insight-card.component';

@Component({
  standalone: true,
  imports: [SpikeInsightCardComponent],
  template: `
    <app-spike-insight-card
      [tone]="tone"
      [headline]="headline"
      [detail]="detail"
      [actionLabel]="actionLabel"
      [actionLink]="actionLink"
    />
  `,
})
class HostComponent {
  tone: 'info' | 'warning' | 'success' = 'warning';
  headline = 'System health needs attention';
  detail = 'Some services are degraded';
  actionLabel: string | null = 'View system health';
  actionLink: string | null = '/health';
}

describe('SpikeInsightCardComponent (CDK + Tailwind)', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const q = (sel: string) => fixture.nativeElement.querySelector(sel);

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renders the headline and detail', () => {
    expect(fixture.nativeElement.textContent).toContain('System health needs attention');
    expect(fixture.nativeElement.textContent).toContain('Some services are degraded');
  });

  it('renders an owned app-icon (no mat-icon)', () => {
    expect(q('app-icon')).toBeTruthy();
    expect(q('mat-icon')).toBeNull();
  });

  it('renders a routed action button (no mat-button)', () => {
    const a = q('a');
    expect(a).toBeTruthy();
    expect(a.getAttribute('href')).toContain('/health');
    expect(a.textContent).toContain('View system health');
  });

  it('omits the action when no link is given', () => {
    host.actionLink = null;
    fixture.detectChanges();
    expect(q('a')).toBeNull();
  });

  it('omits the detail line when empty', () => {
    host.detail = '';
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Some services are degraded');
  });
});
