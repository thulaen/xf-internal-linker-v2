import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Eli5CardComponent } from './eli5-card.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('Eli5CardComponent', () => {
  let component: Eli5CardComponent;
  let fixture: ComponentFixture<Eli5CardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Eli5CardComponent, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(Eli5CardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render an initial concept', () => {
    const title = fixture.nativeElement.querySelector('mat-card-subtitle');
    const text = fixture.nativeElement.querySelector('.eli5-text');
    expect(title.textContent).toBeTruthy();
    expect(text.textContent).toBeTruthy();
  });

  it('should rotate to a new concept when "Another concept" is clicked', () => {
    const initialId = component.current()?.id;
    const button = fixture.nativeElement.querySelector('button');
    
    button.click();
    fixture.detectChanges();
    
    const newId = component.current()?.id;
    // Note: random chance it picks the same one if pool is small, 
    // but the component logic filters out the current id.
    expect(newId).not.toBe(initialId);
  });

  it('should render the refresh icon in the action button', () => {
    const icon = fixture.nativeElement.querySelector('mat-card-actions mat-icon');
    expect(icon.textContent).toContain('refresh');
  });
});
