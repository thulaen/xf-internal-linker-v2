import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RankingStrategyCardComponent, ChallengerRow } from './ranking-strategy-card.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('RankingStrategyCardComponent', () => {
  let component: RankingStrategyCardComponent;
  let fixture: ComponentFixture<RankingStrategyCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RankingStrategyCardComponent, NoopAnimationsModule],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(RankingStrategyCardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should show "no challengers" message when empty', () => {
    component.challengers = [];
    fixture.detectChanges();
    const noChallengers = fixture.debugElement.query(By.css('.no-challengers'));
    expect(noChallengers).toBeTruthy();
    expect(noChallengers.nativeElement.textContent).toContain('No challengers running');
  });

  it('should render challenger list when data is provided', () => {
    const mockChallengers: ChallengerRow[] = [
      { id: 1, name: 'Model A', status: 'ready' },
      { id: 2, status: 'running' }
    ];
    fixture.componentRef.setInput('challengers', mockChallengers);
    fixture.detectChanges();

    const rows = fixture.debugElement.queryAll(By.css('.challenger-row'));
    expect(rows.length).toBe(2);
    expect(rows[0].nativeElement.textContent).toContain('Model A');
    expect(rows[1].nativeElement.textContent).toContain('Challenger 2');
    expect(rows[1].nativeElement.textContent).toContain('running');
  });

  it('should correctly link to settings', () => {
    const settingsLink = fixture.debugElement.query(By.css('a[routerLink="/settings"]'));
    expect(settingsLink).toBeTruthy();
    expect(settingsLink.nativeElement.getAttribute('fragment')).toBe('ranking-weights');
  });
});
