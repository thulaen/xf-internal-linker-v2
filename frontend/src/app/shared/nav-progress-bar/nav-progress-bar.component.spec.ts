import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Subject } from 'rxjs';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationStart,
  Router,
} from '@angular/router';

import { NavProgressBarComponent } from './nav-progress-bar.component';

describe('NavProgressBarComponent', () => {
  let fixture: ComponentFixture<NavProgressBarComponent>;
  let routerEvents$: Subject<NavigationStart | NavigationEnd | NavigationCancel>;

  beforeEach(async () => {
    routerEvents$ = new Subject();

    await TestBed.configureTestingModule({
      imports: [NavProgressBarComponent],
      providers: [
        { provide: Router, useValue: { events: routerEvents$.asObservable() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(NavProgressBarComponent);
    fixture.detectChanges();
  });

  it('hides the progress bar by default', () => {
    expect(fixture.debugElement.query(By.css('mat-progress-bar'))).toBeNull();
  });

  it('shows the bar when NavigationStart fires', () => {
    routerEvents$.next(new NavigationStart(1, '/test'));
    fixture.detectChanges();
    expect(fixture.debugElement.query(By.css('mat-progress-bar'))).toBeTruthy();
  });

  it('hides the bar when NavigationEnd fires after a start', () => {
    routerEvents$.next(new NavigationStart(1, '/test'));
    fixture.detectChanges();
    routerEvents$.next(new NavigationEnd(1, '/test', '/test'));
    fixture.detectChanges();
    expect(fixture.debugElement.query(By.css('mat-progress-bar'))).toBeNull();
  });

  it('hides the bar when NavigationCancel fires after a start', () => {
    routerEvents$.next(new NavigationStart(1, '/test'));
    fixture.detectChanges();
    routerEvents$.next(new NavigationCancel(1, '/test', 'guard blocked'));
    fixture.detectChanges();
    expect(fixture.debugElement.query(By.css('mat-progress-bar'))).toBeNull();
  });
});
