import { ComponentFixture, TestBed } from '@angular/core/testing';
import { YouAreHereComponent } from './you-are-here.component';
import { Router, NavigationEnd } from '@angular/router';
import { Subject } from 'rxjs';

describe('YouAreHereComponent', () => {
  let component: YouAreHereComponent;
  let fixture: ComponentFixture<YouAreHereComponent>;
  let routerMock: jasmine.SpyObj<Router>;
  let routerEvents: Subject<any>;

  beforeEach(async () => {
    routerEvents = new Subject();
    routerMock = jasmine.createSpyObj('Router', ['events'], {
      url: '/dashboard'
    });
    (routerMock as any).events = routerEvents.asObservable();

    await TestBed.configureTestingModule({
      imports: [YouAreHereComponent],
      providers: [
        { provide: Router, useValue: routerMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(YouAreHereComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display the current route label and icon', () => {
    const label = fixture.nativeElement.querySelector('.yah-label');
    const icon = fixture.nativeElement.querySelector('.yah-icon');
    expect(label.textContent).toBe('Dashboard');
    expect(icon.textContent).toBe('dashboard');
  });

  it('should update on navigation', () => {
    routerEvents.next(new NavigationEnd(1, '/settings', '/settings'));
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.yah-label');
    const icon = fixture.nativeElement.querySelector('.yah-icon');
    expect(label.textContent).toBe('Settings');
    expect(icon.textContent).toBe('settings');
  });

  it('should fallback for unknown routes', () => {
    routerEvents.next(new NavigationEnd(2, '/unknown', '/unknown'));
    fixture.detectChanges();

    const label = fixture.nativeElement.querySelector('.yah-label');
    expect(label.textContent).toBe('/unknown');
  });
});
