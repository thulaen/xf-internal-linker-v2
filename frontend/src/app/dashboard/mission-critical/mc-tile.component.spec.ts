import { ComponentFixture, TestBed } from '@angular/core/testing';
import { McTileComponent } from './mc-tile.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { McTile } from './mc-types';

describe('McTileComponent', () => {
  let component: McTileComponent;
  let fixture: ComponentFixture<McTileComponent>;

  const mockTile: McTile = {
    id: 'pipeline',
    name: 'Pipeline',
    state: 'WORKING',
    plain_english: 'All systems operational.',
    last_action_at: null,
    progress: 0.85,
    actions: ['Restart'],
    group: null,
    root_cause: null,
    uptime_pct_24h: 99.9,
    health_grade: 'A'
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [McTileComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(McTileComponent);
    component = fixture.componentInstance;
    component.tile = mockTile;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render tile name and state', () => {
    const nameEl = fixture.nativeElement.querySelector('.mc-name');
    const stateEl = fixture.nativeElement.querySelector('.mc-state-chip');
    expect(nameEl.textContent).toContain('Pipeline');
    expect(stateEl.textContent).toContain('WORKING');
  });

  it('should emit tileClick when clicked', () => {
    vi.spyOn(component.tileClick, 'emit').mockReturnValue(undefined as never);
    fixture.nativeElement.querySelector('.mc-tile').click();
    expect(component.tileClick.emit).toHaveBeenCalledWith(mockTile);
  });

  it('should emit action when action button is clicked', () => {
    vi.spyOn(component.action, 'emit').mockReturnValue(undefined as never);
    const button = fixture.nativeElement.querySelector('.mc-actions button');
    button.click();
    expect(component.action.emit).toHaveBeenCalledWith({ tile: mockTile, action: 'Restart' });
  });

  it('should truncate long messages', () => {
    const longMsg = 'A'.repeat(200);
    expect(component.truncateMsg(longMsg)).toContain('…');
    expect(component.truncateMsg('short')).toBe('short');
  });

  it('should format ETA correctly', () => {
    expect(component.formatEta(45)).toBe('45s');
    expect(component.formatEta(125)).toBe('2m 5s');
    expect(component.formatEta(3600)).toBe('~1h');
  });
});
