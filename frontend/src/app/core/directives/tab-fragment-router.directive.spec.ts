import { Component, ChangeDetectionStrategy } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatTabGroup, MatTabsModule } from '@angular/material/tabs';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { Subject } from 'rxjs';
import { TabFragmentRouterDirective } from './tab-fragment-router.directive';

@Component({
  standalone: true,
  imports: [MatTabsModule, TabFragmentRouterDirective],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <mat-tab-group appTabFragment [tabFragmentMap]="map" [selectedIndex]="initial">
      <mat-tab label="A">A body</mat-tab>
      <mat-tab label="B">B body</mat-tab>
      <mat-tab label="C">C body</mat-tab>
    </mat-tab-group>
  `,
})
class HostComponent {
  map: Record<string, number> = { 'tab-a': 0, 'tab-b': 1, 'tab-c': 2 };
  initial = 0;
}

describe('TabFragmentRouterDirective', () => {
  let fixture: ComponentFixture<HostComponent>;
  let routerEvents$: Subject<unknown>;
  let snapshot: {
    fragment: string | null;
    queryParamMap: { get: (k: string) => string | null };
  };

  beforeEach(() => {
    routerEvents$ = new Subject<unknown>();
    snapshot = {
      fragment: null,
      queryParamMap: { get: () => null },
    };

    TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [
        provideNoopAnimations(),
        { provide: Router, useValue: { events: routerEvents$.asObservable() } },
        { provide: ActivatedRoute, useValue: { snapshot } },
      ],
    });
    fixture = TestBed.createComponent(HostComponent);
  });

  function getMatTabGroup(): MatTabGroup {
    return fixture.debugElement.query(By.directive(MatTabGroup)).componentInstance as MatTabGroup;
  }

  it('switches to the tab matching the URL fragment after a NavigationEnd', fakeAsync(() => {
    fixture.detectChanges();
    expect(getMatTabGroup().selectedIndex).toBe(0);

    snapshot.fragment = 'tab-c';
    routerEvents$.next(new NavigationEnd(1, '/#tab-c', '/#tab-c'));
    tick();
    fixture.detectChanges();

    expect(getMatTabGroup().selectedIndex).toBe(2);
  }));

  it('switches to the tab matching the ?tab= query parameter', fakeAsync(() => {
    fixture.detectChanges();

    snapshot.queryParamMap = {
      get: (k: string) => (k === 'tab' ? 'tab-b' : null),
    };
    routerEvents$.next(new NavigationEnd(1, '/?tab=tab-b', '/?tab=tab-b'));
    tick();
    fixture.detectChanges();

    expect(getMatTabGroup().selectedIndex).toBe(1);
  }));

  it('ignores fragments that are not in the map', fakeAsync(() => {
    fixture.detectChanges();
    expect(getMatTabGroup().selectedIndex).toBe(0);

    snapshot.fragment = 'unknown-fragment';
    routerEvents$.next(new NavigationEnd(1, '/#unknown-fragment', '/#unknown-fragment'));
    tick();
    fixture.detectChanges();

    expect(getMatTabGroup().selectedIndex).toBe(0);
  }));

  it('clamps an out-of-range tab index to the last valid tab', fakeAsync(() => {
    fixture.componentInstance.map = { 'beyond-end': 5 };
    fixture.detectChanges();

    snapshot.fragment = 'beyond-end';
    routerEvents$.next(new NavigationEnd(1, '/#beyond-end', '/#beyond-end'));
    tick();
    fixture.detectChanges();

    expect(getMatTabGroup().selectedIndex).toBe(2);
  }));

  it('survives a missing queryParamMap on the snapshot (defensive)', fakeAsync(() => {
    snapshot = {
      fragment: 'tab-a',
      queryParamMap: undefined as unknown as { get: (k: string) => string | null },
    };
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [
        provideNoopAnimations(),
        { provide: Router, useValue: { events: routerEvents$.asObservable() } },
        { provide: ActivatedRoute, useValue: { snapshot } },
      ],
    });
    fixture = TestBed.createComponent(HostComponent);

    expect(() => {
      fixture.detectChanges();
      tick();
    }).not.toThrow();
  }));
});
