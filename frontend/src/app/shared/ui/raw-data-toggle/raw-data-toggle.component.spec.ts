import { Component, ChangeDetectionStrategy } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { RawDataToggleComponent } from './raw-data-toggle.component';

@Component({
  standalone: true,
  imports: [RawDataToggleComponent],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <app-raw-data-toggle [data]="data" label="chart">
      <div class="projected-chart">Chart content</div>
    </app-raw-data-toggle>
  `,
})
class RawDataToggleHostComponent {
  data = { count: 2 };
}

describe('RawDataToggleComponent', () => {
  let fixture: ComponentFixture<RawDataToggleHostComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RawDataToggleHostComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(RawDataToggleHostComponent);
    fixture.detectChanges();
  });

  it('renders projected content by default', () => {
    expect(fixture.debugElement.query(By.css('.projected-chart'))).toBeTruthy();
    expect(fixture.debugElement.query(By.css('.rdt-json'))).toBeNull();
  });

  it('toggles to formatted raw data and back', () => {
    const button = fixture.debugElement.query(By.css('button'));

    button.nativeElement.click();
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.projected-chart'))).toBeNull();
    expect(fixture.debugElement.query(By.css('.rdt-json')).nativeElement.textContent).toContain('"count": 2');

    button.nativeElement.click();
    fixture.detectChanges();

    expect(fixture.debugElement.query(By.css('.projected-chart'))).toBeTruthy();
    expect(fixture.debugElement.query(By.css('.rdt-json'))).toBeNull();
  });
});
