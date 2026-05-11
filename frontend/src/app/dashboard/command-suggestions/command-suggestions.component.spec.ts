import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CommandSuggestionsComponent } from './command-suggestions.component';
import { provideRouter } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('CommandSuggestionsComponent', () => {
  let component: CommandSuggestionsComponent;
  let fixture: ComponentFixture<CommandSuggestionsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CommandSuggestionsComponent, NoopAnimationsModule],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(CommandSuggestionsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should filter matches based on query', () => {
    component.onQueryChange('sync');
    expect(component.matches().length).toBeGreaterThan(0);
    expect(component.matches()[0].action).toContain('Run an import / sync');
  });

  it('should be case-insensitive', () => {
    component.onQueryChange('IMPORT');
    expect(component.matches().length).toBeGreaterThan(0);
    expect(component.matches()[0].action).toContain('Run an import / sync');
  });

  it('should show "No match" when no intent matches', () => {
    component.query = 'xyz123';
    component.onQueryChange(component.query);
    fixture.detectChanges();
    expect(component.matches().length).toBe(0);
    expect(component.query).toBe('xyz123');
  });

  it('should reset query on pick', () => {
    const mockIntent = { keywords: ['test'], action: 'Test Action', route: '/test', icon: 'test' };
    component.query = 'test';
    component.onPick(mockIntent);
    expect(component.query).toBe('');
    expect(component.matches().length).toBe(0);
  });

  it('should fuzzy match keywords and action text', () => {
    // "broken" matches "Scan for broken links" (keywords ['broken', 'link', 'fix', 'scan'])
    component.onQueryChange('broken');
    expect(component.matches().some(m => m.action.includes('broken'))).toBeTrue();

    // "report" matches "Open Analytics reports" (keywords ['analytics', 'traffic', 'impressions', 'clicks'])
    // Wait, "report" is in the action text "Open Analytics reports"
    component.onQueryChange('report');
    expect(component.matches().some(m => m.action.includes('Analytics reports'))).toBeTrue();
  });
});
