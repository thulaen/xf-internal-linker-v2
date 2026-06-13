import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormWizardComponent, FormWizardStepComponent, WizardStepContentDirective } from './wizard.component';
import { Component, ChangeDetectionStrategy } from '@angular/core';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

@Component({
  template: `
    <app-form-wizard (finished)="onFinish()">
      <app-form-wizard-step label="Step 1" [valid]="step1Valid">
        <ng-template appWizardStepContent>
          <div id="content1">Step 1 Content</div>
        </ng-template>
      </app-form-wizard-step>
      <app-form-wizard-step label="Step 2">
        <ng-template appWizardStepContent>
          <div id="content2">Step 2 Content</div>
        </ng-template>
      </app-form-wizard-step>
    </app-form-wizard>
  `,
  standalone: true,
  changeDetection: ChangeDetectionStrategy.Eager,
  imports: [FormWizardComponent, FormWizardStepComponent, WizardStepContentDirective],
})
class TestHostComponent {
  step1Valid = true;
  finished = false;
  onFinish() {
    this.finished = true;
  }
}

describe('FormWizardComponent', () => {
  let fixture: ComponentFixture<TestHostComponent>;
  let host: TestHostComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHostComponent, NoopAnimationsModule],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHostComponent);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should render the first step content', () => {
    expect(fixture.nativeElement.querySelector('#content1')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('#content2')).toBeFalsy();
  });

  it('should navigate to the next step when valid', () => {
    const nextBtn = fixture.nativeElement.querySelector('.fw-footer button:last-child');
    nextBtn.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('#content1')).toBeFalsy();
    expect(fixture.nativeElement.querySelector('#content2')).toBeTruthy();
  });

  it('should disable next button if step is invalid', () => {
    host.step1Valid = false;
    fixture.detectChanges();
    fixture.detectChanges();

    const nextBtn = fixture.nativeElement.querySelector('.fw-footer button:last-child');
    expect(nextBtn.disabled).toBe(true);
  });

  it('should emit finished on last step', () => {
    // Go to step 2
    fixture.nativeElement.querySelector('.fw-footer button:last-child').click();
    fixture.detectChanges();

    // Click finish
    const finishBtn = fixture.nativeElement.querySelector('.fw-footer button:last-child');
    expect(finishBtn.textContent).toContain('Finish');
    finishBtn.click();

    expect(host.finished).toBe(true);
  });

  it('should allow jumping back to a reached step', () => {
    // Go to step 2
    fixture.nativeElement.querySelector('.fw-footer button:last-child').click();
    fixture.detectChanges();

    // Click step 1 crumb
    const crumbs = fixture.nativeElement.querySelectorAll('.fw-crumb-btn');
    crumbs[0].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('#content1')).toBeTruthy();
  });
});
