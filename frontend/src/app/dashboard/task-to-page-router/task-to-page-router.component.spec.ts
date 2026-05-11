import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TaskToPageRouterComponent } from './task-to-page-router.component';
import { Router } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('TaskToPageRouterComponent', () => {
  let component: TaskToPageRouterComponent;
  let fixture: ComponentFixture<TaskToPageRouterComponent>;
  let mockRouter: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    mockRouter = jasmine.createSpyObj('Router', ['navigate']);

    await TestBed.configureTestingModule({
      imports: [TaskToPageRouterComponent, NoopAnimationsModule],
      providers: [
        { provide: Router, useValue: mockRouter }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(TaskToPageRouterComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have predefined intent groups', () => {
    expect(component.groups.length).toBeGreaterThan(0);
    expect(component.groups[0].heading).toBe('Review');
  });

  it('should navigate to correct route when option is picked', () => {
    const mockOption = { label: 'Test', route: '/test', fragment: 'feat', icon: 'star' };
    component.onPick(mockOption);
    
    expect(mockRouter.navigate).toHaveBeenCalledWith(['/test'], { fragment: 'feat' });
  });

  it('should reset selected after navigation', (done) => {
    const mockOption = { label: 'Test', route: '/test', icon: 'star' };
    component.selected = mockOption;
    component.onPick(mockOption);
    
    // queueMicrotask is used in the component
    setTimeout(() => {
      expect(component.selected).toBeNull();
      done();
    }, 0);
  });
});
