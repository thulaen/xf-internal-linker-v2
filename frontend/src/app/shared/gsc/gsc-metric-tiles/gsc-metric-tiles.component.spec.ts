import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { GscMetricTilesComponent, GscTile } from './gsc-metric-tiles.component';

@Component({
  standalone: true,
  imports: [GscMetricTilesComponent],
  template: `<app-gsc-metric-tiles [tiles]="tiles" />`,
})
class HostComponent {
  tiles: GscTile[] = [
    { label: 'Pending', value: 5, tone: 'blue' },
    { label: 'Approved', value: 3, tone: 'green' },
    { label: 'Total', value: 8 },
  ];
}

describe('GscMetricTilesComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  const tiles = () => fixture.nativeElement.querySelectorAll('.gsc-tile');

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HostComponent, NoopAnimationsModule],
    }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('Given a list of metric tiles, When the component renders, Then it creates one tile element per item', () => {
    expect(tiles().length).toBe(3);
  });

  it('Given a tile object, When rendered, Then the tile label and value are displayed', () => {
    const first = tiles()[0];
    expect(first.querySelector('.gsc-tile__label').textContent).toContain('Pending');
    expect(first.querySelector('.gsc-tile__value').textContent).toContain('5');
  });

  it('Given tiles with specific tones, When rendered, Then each filled tile has the matching tone class', () => {
    expect(tiles()[0].classList).toContain('tone-blue');
    expect(tiles()[1].classList).toContain('tone-green');
  });

  it('Given a tile without a tone, When rendered, Then it lacks any tone class', () => {
    const third = tiles()[2];
    expect([...third.classList].some((c: string) => c.startsWith('tone-'))).toBe(false);
  });

  it('Given an updated tiles array, When change detection runs, Then the rendered tiles match the new input', () => {
    host.tiles = [{ label: 'Only', value: 1, tone: 'purple' }];
    fixture.detectChanges();
    expect(tiles().length).toBe(1);
    expect(tiles()[0].classList).toContain('tone-purple');
  });
});
