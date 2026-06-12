import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { GscInsightCardComponent } from './gsc-insight-card.component';

@Component({
  standalone: true,
  imports: [GscInsightCardComponent],
  template: `
    <app-gsc-insight-card
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
  headline = 'Fix issues before running the pipeline';
  detail = 'System health is degraded';
  actionLabel: string | null = 'Fix';
  actionLink: string | null = '/health';
}

describe('GscInsightCardComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const q = (sel: string) => fixture.nativeElement.querySelector(sel);

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent, NoopAnimationsModule],
      providers: [provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('Given a headline and detail, When the insight card renders, Then both texts are displayed', () => {
    expect(q('.gsc-insight__headline').textContent).toContain(
      'Fix issues before running the pipeline',
    );
    expect(q('.gsc-insight__detail').textContent).toContain('System health is degraded');
  });

  it('Given a tone, When the card renders, Then it applies the corresponding tone class to the wrapper', () => {
    expect(q('.gsc-insight').classList).toContain('tone-warning');
    host.tone = 'success';
    fixture.detectChanges();
    expect(q('.gsc-insight').classList).toContain('tone-success');
  });

  it('Given an action link and label, When the card renders, Then an anchor tag points to the route', () => {
    const action = q('a.gsc-insight__action');
    expect(action).toBeTruthy();
    expect(action.getAttribute('href')).toContain('/health');
    expect(action.textContent).toContain('Fix');
  });

  it('Given no action link, When the card renders, Then the action anchor tag is omitted', () => {
    host.actionLink = null;
    fixture.detectChanges();
    expect(q('a.gsc-insight__action')).toBeNull();
  });

  it('Given an empty detail line, When the card renders, Then the detail element is omitted', () => {
    host.detail = '';
    fixture.detectChanges();
    expect(q('.gsc-insight__detail')).toBeNull();
  });
});
