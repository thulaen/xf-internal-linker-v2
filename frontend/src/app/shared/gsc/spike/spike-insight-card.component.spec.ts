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

  it('Given a headline and detail, When the card renders, Then both strings are present in the text content', () => {
    expect(fixture.nativeElement.textContent).toContain('System health needs attention');
    expect(fixture.nativeElement.textContent).toContain('Some services are degraded');
  });

  it('Given the component uses CDK + Tailwind, When rendered, Then it uses app-icon instead of mat-icon', () => {
    expect(q('app-icon')).toBeTruthy();
    expect(q('mat-icon')).toBeNull();
  });

  it('Given a routed action, When rendered, Then it uses a standard anchor tag instead of mat-button', () => {
    const a = q('a');
    expect(a).toBeTruthy();
    expect(a.getAttribute('href')).toContain('/health');
    expect(a.textContent).toContain('View system health');
  });

  it('Given no action link, When rendered, Then the action anchor is omitted', () => {
    host.actionLink = null;
    fixture.detectChanges();
    expect(q('a')).toBeNull();
  });

  it('Given an empty detail, When rendered, Then the detail text is omitted from the output', () => {
    host.detail = '';
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Some services are degraded');
  });
});
