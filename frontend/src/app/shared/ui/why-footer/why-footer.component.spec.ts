import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WhyFooterComponent } from './why-footer.component';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('WhyFooterComponent', () => {
  let component: WhyFooterComponent;
  let fixture: ComponentFixture<WhyFooterComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WhyFooterComponent, NoopAnimationsModule]
    }).compileComponents();

    fixture = TestBed.createComponent(WhyFooterComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render the provided text', () => {
    component.text = 'This is an explanation.';
    fixture.detectChanges();

    const textEl = fixture.nativeElement.querySelector('.wf-text');
    expect(textEl.textContent).toBe('This is an explanation.');
  });

  it('should render the fixed label', () => {
    component.text = 'test';
    fixture.detectChanges();

    const labelEl = fixture.nativeElement.querySelector('.wf-label');
    expect(labelEl.textContent).toBe('Why am I seeing this?');
  });
});
