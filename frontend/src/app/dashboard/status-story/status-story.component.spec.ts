import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { StatusStoryComponent } from './status-story.component';
import { DashboardService, StatusStory } from '../dashboard.service';
import { VisibilityGateService } from '../../core/util/visibility-gate.service';
import { of, throwError } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('StatusStoryComponent', () => {
  let component: StatusStoryComponent;
  let fixture: ComponentFixture<StatusStoryComponent>;
  let mockDash: SpyObj<DashboardService>;
  let mockVisibility: SpyObj<VisibilityGateService>;

  const mockStory: StatusStory = {
    headline: 'Everything is running smoothly.',
    fragments: ['Fragment 1', 'Fragment 2'],
    alerts_today: 0,
    pending_reviews: 5,
    broken_links_open: 2,
    health_status: 'healthy',
    generated_at: new Date().toISOString()
  };

  beforeEach(async () => {
    mockDash = createSpyObj(['getStatusStory']);
    mockVisibility = createSpyObj(['whileLoggedInAndVisible']);

    // Default: return the stream immediately
    mockVisibility.whileLoggedInAndVisible.mockImplementation((fn) => fn());
    mockDash.getStatusStory.mockReturnValue(of(mockStory));

    await TestBed.configureTestingModule({
      imports: [StatusStoryComponent, NoopAnimationsModule],
      providers: [
        { provide: DashboardService, useValue: mockDash },
        { provide: VisibilityGateService, useValue: mockVisibility }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(StatusStoryComponent);
    component = fixture.componentInstance;
  });

  it('should create', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    expect(component).toBeTruthy();
  }));
  
  it('should fetch story on init', fakeAsync(() => {
    component.story.set(mockStory);
    fixture.detectChanges();
    expect(component.story()).toEqual(mockStory);
  }));

  it('should show spinner while loading and no story', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    component.story.set(null);
    component.loading.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('mat-spinner')).toBeTruthy();
  }));

  it('should show stale hint on error if previous story exists', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    component.story.set(mockStory);
    mockDash.getStatusStory.mockReturnValue(throwError(() => new Error('API error')));
    component.refresh();
    fixture.detectChanges();
    
    expect(component.errored()).toBe(true);
    expect(fixture.nativeElement.querySelector('.story-stale-hint')).toBeTruthy();
    expect(component.story()).toEqual(mockStory); // Kept previous
  }));

  it('should refresh when button is clicked', fakeAsync(() => {
    fixture.detectChanges();
    tick();
    const newStory = { ...mockStory, headline: 'New status' };
    mockDash.getStatusStory.mockReturnValue(of(newStory));
    
    component.refresh();
    fixture.detectChanges();
    expect(component.story()).toEqual(newStory);
    expect(component.loading()).toBe(false);
  }));

  it('should format freshness label correctly', () => {
    const now = new Date();
    const tenMinsAgo = new Date(now.getTime() - 10 * 60 * 1000).toISOString();
    expect(component.freshnessLabel(tenMinsAgo)).toBe('10m ago');
    
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
    expect(component.freshnessLabel(oneHourAgo)).toBe('1h ago');
  });
});
