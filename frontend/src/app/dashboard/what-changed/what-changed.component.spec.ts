import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WhatChangedComponent, WhatChangedData } from './what-changed.component';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('WhatChangedComponent', () => {
  let component: WhatChangedComponent;
  let fixture: ComponentFixture<WhatChangedComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WhatChangedComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(WhatChangedComponent);
    component = fixture.componentInstance;
  });

  it('should render initial metrics correctly', () => {
    const mockData: WhatChangedData = {
      new_suggestions: 10,
      reviewed: 5,
      items_synced: 100,
      pipeline_runs: 2
    };
    component.changes = mockData;
    fixture.detectChanges();

    const values = fixture.debugElement.queryAll(By.css('.metric-value'))
      .map(el => el.nativeElement.textContent.trim());
    
    expect(values).toContain('10');
    expect(values).toContain('5');
    expect(values).toContain('100');
    expect(values).toContain('2');
  });

  it('should show autotuner row if outcome is present', () => {
    component.changes = {
      new_suggestions: 0, reviewed: 0, items_synced: 0, pipeline_runs: 0,
      autotuner_outcome: 'Weights adjusted for freshness'
    };
    fixture.detectChanges();

    const autotunerRow = fixture.debugElement.query(By.css('.autotuner-row'));
    expect(autotunerRow).toBeTruthy();
    expect(autotunerRow.nativeElement.textContent).toContain('Weights adjusted for freshness');
  });

  it('should hide autotuner row if outcome is missing', () => {
    component.changes = {
      new_suggestions: 0, reviewed: 0, items_synced: 0, pipeline_runs: 0
    };
    fixture.detectChanges();

    const autotunerRow = fixture.debugElement.query(By.css('.autotuner-row'));
    expect(autotunerRow).toBeNull();
  });
});
