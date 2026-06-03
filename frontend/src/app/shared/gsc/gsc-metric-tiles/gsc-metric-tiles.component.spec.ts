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

  it('renders one tile per item', () => {
    expect(tiles().length).toBe(3);
  });

  it('renders each tile label and value', () => {
    const first = tiles()[0];
    expect(first.querySelector('.gsc-tile__label').textContent).toContain('Pending');
    expect(first.querySelector('.gsc-tile__value').textContent).toContain('5');
  });

  it('applies the tone class to filled (coloured) tiles', () => {
    expect(tiles()[0].classList).toContain('tone-blue');
    expect(tiles()[1].classList).toContain('tone-green');
  });

  it('leaves a tile with no tone unfilled (no tone-* class)', () => {
    const third = tiles()[2];
    expect([...third.classList].some((c: string) => c.startsWith('tone-'))).toBeFalse();
  });

  it('updates when the tiles input changes', () => {
    host.tiles = [{ label: 'Only', value: 1, tone: 'purple' }];
    fixture.detectChanges();
    expect(tiles().length).toBe(1);
    expect(tiles()[0].classList).toContain('tone-purple');
  });
});
