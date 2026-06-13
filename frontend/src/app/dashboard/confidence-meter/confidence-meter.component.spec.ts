import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient, withXhr } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { ConfidenceMeterComponent } from './confidence-meter.component';
import { ConfidenceContributor, ConfidenceSnapshot } from '../dashboard.service';

function snapshot(total: number, contributors: ConfidenceContributor[] = []): ConfidenceSnapshot {
  return { total, label: 'x', contributors };
}

describe('ConfidenceMeterComponent', () => {
  let fixture: ComponentFixture<ConfidenceMeterComponent>;
  let component: ConfidenceMeterComponent;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfidenceMeterComponent],
      providers: [provideHttpClient(withXhr()), provideHttpClientTesting(), provideRouter([]), provideNoopAnimations()],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfidenceMeterComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders without throwing when snapshot is null', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(component.tone()).toBe('red');
    expect(component.contributorCount()).toBe(0);
  });

  it('maps total to the right tone bucket', () => {
    fixture.componentRef.setInput('snapshot', snapshot(95));
    expect(component.tone()).toBe('green');
    expect(component.toneIcon()).toBe('rocket_launch');

    fixture.componentRef.setInput('snapshot', snapshot(75));
    expect(component.tone()).toBe('amber');

    fixture.componentRef.setInput('snapshot', snapshot(50));
    expect(component.tone()).toBe('orange');

    fixture.componentRef.setInput('snapshot', snapshot(10));
    expect(component.tone()).toBe('red');
  });

  it('sorts weakest contributors by lost-points descending', () => {
    const contribs: ConfidenceContributor[] = [
      { name: 'a', label: 'A', score: 0.9, points: 9, max_pts: 10, fix_hint: '' },
      { name: 'b', label: 'B', score: 0.1, points: 1, max_pts: 10, fix_hint: '' },
      { name: 'c', label: 'C', score: 1.0, points: 10, max_pts: 10, fix_hint: '' },
    ];
    fixture.componentRef.setInput('snapshot', snapshot(20, contribs));
    const weak = component.weakestContributors();
    expect(weak.length).toBe(2);
    expect(weak[0].name).toBe('b'); // lost 9 — biggest
    expect(weak[1].name).toBe('a'); // lost 1
    expect(component.trackByName(0, contribs[0])).toBe('a');
  });
});
