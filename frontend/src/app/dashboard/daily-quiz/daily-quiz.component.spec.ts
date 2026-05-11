import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DailyQuizComponent } from './daily-quiz.component';

describe('DailyQuizComponent', () => {
  let component: DailyQuizComponent;
  let fixture: ComponentFixture<DailyQuizComponent>;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [DailyQuizComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(DailyQuizComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('should create', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should render a question', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.quiz-prompt')).toBeTruthy();
    expect(compiled.querySelectorAll('.quiz-option').length).toBeGreaterThan(0);
  });

  it('should reveal explanation after answering', () => {
    fixture.detectChanges();
    expect(component.answered()).toBeFalse();
    
    component.answer(0);
    fixture.detectChanges();
    
    expect(component.answered()).toBeTrue();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.quiz-explanation')).toBeTruthy();
  });

  it('should disable buttons after answering', () => {
    fixture.detectChanges();
    component.answer(0);
    fixture.detectChanges();
    
    const buttons = fixture.nativeElement.querySelectorAll('.quiz-option');
    buttons.forEach((btn: HTMLButtonElement) => {
      expect(btn.disabled).toBeTrue();
    });
  });

  it('should apply correct/wrong classes on answers', () => {
    fixture.detectChanges();
    const correctIdx = component.question().correctIndex;
    const wrongIdx = (correctIdx + 1) % component.question().options.length;
    
    component.answer(wrongIdx);
    fixture.detectChanges();
    
    const options = fixture.nativeElement.querySelectorAll('.quiz-option');
    expect(options[correctIdx].classList).toContain('quiz-correct');
    expect(options[wrongIdx].classList).toContain('quiz-wrong');
  });
});
