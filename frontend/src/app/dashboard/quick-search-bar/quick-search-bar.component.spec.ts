import { ComponentFixture, TestBed } from '@angular/core/testing';
import { QuickSearchBarComponent } from './quick-search-bar.component';
import { CommandPaletteService } from '../../shared/services/command-palette.service';

describe('QuickSearchBarComponent', () => {
  let component: QuickSearchBarComponent;
  let fixture: ComponentFixture<QuickSearchBarComponent>;
  let mockPalette: SpyObj<CommandPaletteService>;

  beforeEach(async () => {
    mockPalette = createSpyObj(['toggle']);

    await TestBed.configureTestingModule({
      imports: [QuickSearchBarComponent],
      providers: [
        { provide: CommandPaletteService, useValue: mockPalette }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(QuickSearchBarComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should call palette.toggle() on click', () => {
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button.qsb');
    button.click();
    expect(mockPalette.toggle).toHaveBeenCalled();
  });

  it('should render the correct shortcut label', () => {
    fixture.detectChanges();
    const kbd = fixture.nativeElement.querySelector('kbd');
    const label = kbd.textContent?.trim();
    // In test environment, it depends on the navigator.userAgent
    expect(['Ctrl+K', '⌘K']).toContain(label!);
  });

  it('should have a search icon', () => {
    fixture.detectChanges();
    const icon = fixture.nativeElement.querySelector('.qsb-icon');
    expect(icon.textContent?.trim()).toBe('search');
  });
});
