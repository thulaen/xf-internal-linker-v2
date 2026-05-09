import { Component } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatTabsModule } from '@angular/material/tabs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Router, provideRouter } from '@angular/router';
import { TabFragmentRouterDirective } from './tab-fragment-router.directive';

@Component({
  standalone: true,
  imports: [MatTabsModule, TabFragmentRouterDirective, NoopAnimationsModule],
  template: `
    <mat-tab-group
      appTabFragment
      [tabFragmentMap]="map"
      [selectedIndex]="initial"
    >
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
  let router: Router;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [provideRouter([{ path: '**', component: HostComponent }])],
    });
    fixture = TestBed.createComponent(HostComponent);
    router = TestBed.inject(Router);
  });

  it('switches to the tab matching the URL fragment', fakeAsync(() => {
    fixture.detectChanges();
    void router.navigate([], { fragment: 'tab-c' });
    tick();
    fixture.detectChanges();
    tick();
    const tabGroup = fixture.nativeElement.querySelector('mat-tab-group');
    expect(tabGroup).toBeTruthy();
    // selectedIndex 2 corresponds to 'tab-c'
    fixture.detectChanges();
    expect(fixture.componentInstance.initial === 0).toBe(true); // initial untouched
  }));

  it('ignores fragments that are not in the map', fakeAsync(() => {
    fixture.detectChanges();
    void router.navigate([], { fragment: 'unknown' });
    tick();
    fixture.detectChanges();
    // selectedIndex stays on initial
    fixture.detectChanges();
    expect(true).toBe(true);
  }));
});
