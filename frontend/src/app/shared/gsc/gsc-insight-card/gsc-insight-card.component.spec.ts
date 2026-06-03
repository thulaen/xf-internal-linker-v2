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

  it('renders the headline and detail', () => {
    expect(q('.gsc-insight__headline').textContent).toContain(
      'Fix issues before running the pipeline',
    );
    expect(q('.gsc-insight__detail').textContent).toContain('System health is degraded');
  });

  it('applies the tone class', () => {
    expect(q('.gsc-insight').classList).toContain('tone-warning');
    host.tone = 'success';
    fixture.detectChanges();
    expect(q('.gsc-insight').classList).toContain('tone-success');
  });

  it('renders the action link to the provided route', () => {
    const action = q('a.gsc-insight__action');
    expect(action).toBeTruthy();
    expect(action.getAttribute('href')).toContain('/health');
    expect(action.textContent).toContain('Fix');
  });

  it('omits the action when no actionLink is given', () => {
    host.actionLink = null;
    fixture.detectChanges();
    expect(q('a.gsc-insight__action')).toBeNull();
  });

  it('omits the detail line when no detail is given', () => {
    host.detail = '';
    fixture.detectChanges();
    expect(q('.gsc-insight__detail')).toBeNull();
  });
});
