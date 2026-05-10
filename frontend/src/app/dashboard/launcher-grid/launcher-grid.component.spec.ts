import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LauncherGridComponent } from './launcher-grid.component';

describe('LauncherGridComponent', () => {
  let component: LauncherGridComponent;
  let fixture: ComponentFixture<LauncherGridComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LauncherGridComponent],
      providers: [provideRouter([])]
    }).compileComponents();

    fixture = TestBed.createComponent(LauncherGridComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render 6 tiles', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const tiles = compiled.querySelectorAll('.lg-tile');
    expect(tiles.length).toBe(6);
  });

  it('should have correct labels on tiles', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    const labels = Array.from(compiled.querySelectorAll('.lg-tile-label')).map(el => el.textContent?.trim());
    expect(labels).toContain('Review');
    expect(labels).toContain('Settings');
    expect(labels).toContain('Health');
  });
});
