import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ColorLegendComponent } from './color-legend.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('ColorLegendComponent', () => {
  let component: ColorLegendComponent;
  let fixture: ComponentFixture<ColorLegendComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ColorLegendComponent, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(ColorLegendComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render all legend rows', () => {
    const rows = fixture.nativeElement.querySelectorAll('.cl-row');
    expect(rows.length).toBe(5);

    const labels = Array.from(fixture.nativeElement.querySelectorAll('dt')).map((el: any) => el.textContent);
    expect(labels).toContain('Green');
    expect(labels).toContain('Amber');
    expect(labels).toContain('Red');
    expect(labels).toContain('Blue');
    expect(labels).toContain('Grey');
  });

  it('should render swatches with correct classes', () => {
    expect(fixture.nativeElement.querySelector('.cl-swatch-success')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.cl-swatch-warning')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.cl-swatch-error')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.cl-swatch-primary')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.cl-swatch-muted')).toBeTruthy();
  });
});
