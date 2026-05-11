import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TutorialCalloutComponent } from './tutorial-callout.component';
import { TutorialModeService } from '../../../core/services/tutorial-mode.service';
import { signal } from '@angular/core';

describe('TutorialCalloutComponent', () => {
  let component: TutorialCalloutComponent;
  let fixture: ComponentFixture<TutorialCalloutComponent>;
  let tutorialMock: jasmine.SpyObj<TutorialModeService>;
  const enabledSignal = signal(true);
  const isDismissedSignal = signal(false);

  beforeEach(async () => {
    tutorialMock = jasmine.createSpyObj('TutorialModeService', ['dismiss', 'isDismissed'], {
      enabled: enabledSignal
    });
    tutorialMock.isDismissed.and.returnValue(isDismissedSignal);

    await TestBed.configureTestingModule({
      imports: [TutorialCalloutComponent],
      providers: [
        { provide: TutorialModeService, useValue: tutorialMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(TutorialCalloutComponent);
    component = fixture.componentInstance;
    component.cardId = 'test-id';
    component.title = 'Test Title';
    component.body = 'Test Body';
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render when enabled and not dismissed', () => {
    enabledSignal.set(true);
    isDismissedSignal.set(false);
    fixture.detectChanges();

    const aside = fixture.nativeElement.querySelector('.tc');
    expect(aside).toBeTruthy();
    expect(aside.textContent).toContain('Test Title');
  });

  it('should not render when disabled', () => {
    enabledSignal.set(false);
    isDismissedSignal.set(false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.tc')).toBeFalsy();
  });

  it('should not render when dismissed', () => {
    enabledSignal.set(true);
    isDismissedSignal.set(true);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.tc')).toBeFalsy();
  });

  it('should call dismiss on "Got it" click', () => {
    enabledSignal.set(true);
    isDismissedSignal.set(false);
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.tc-dismiss').click();
    expect(tutorialMock.dismiss).toHaveBeenCalledWith('test-id');
  });
});
