import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FlowDiagramComponent } from './flow-diagram.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('FlowDiagramComponent', () => {
  let component: FlowDiagramComponent;
  let fixture: ComponentFixture<FlowDiagramComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FlowDiagramComponent, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(FlowDiagramComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render all five stages', () => {
    const stages = fixture.nativeElement.querySelectorAll('.fd-step');
    expect(stages.length).toBe(5);

    const labels = Array.from(fixture.nativeElement.querySelectorAll('.fd-step-label')).map((el: any) => el.textContent);
    expect(labels).toContain('Source');
    expect(labels).toContain('Crawl & import');
    expect(labels).toContain('Parse & embed');
    expect(labels).toContain('Score & rank');
    expect(labels).toContain('Suggest');
  });

  it('should render connecting arrows', () => {
    const arrows = fixture.nativeElement.querySelectorAll('.fd-arrow');
    expect(arrows.length).toBe(4);
  });
});
