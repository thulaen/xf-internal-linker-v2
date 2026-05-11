import { ComponentFixture, TestBed } from '@angular/core/testing';
import { QuickControlsComponent } from './quick-controls.component';
import { RuntimeModelsService } from '../../admin-models/runtime-models.service';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('QuickControlsComponent', () => {
  let component: QuickControlsComponent;
  let fixture: ComponentFixture<QuickControlsComponent>;
  let svcSpy: jasmine.SpyObj<RuntimeModelsService>;
  let snackSpy: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    svcSpy = jasmine.createSpyObj('RuntimeModelsService', ['list', 'action']);
    snackSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    svcSpy.list.and.returnValue(of({
      task_type: 'embedding',
      active_model: {
        id: 1,
        model_name: 'BGE-M3',
        status: 'ready',
        task_type: 'embedding',
        role: 'champion'
      },
      candidates: [],
      master_paused: false
    } as any));

    await TestBed.configureTestingModule({
      imports: [QuickControlsComponent, NoopAnimationsModule],
      providers: [
        { provide: RuntimeModelsService, useValue: svcSpy },
        { provide: MatSnackBar, useValue: snackSpy },
        provideRouter([])
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(QuickControlsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should list active models on init', () => {
    expect(svcSpy.list).toHaveBeenCalled();
    expect(component.activeModels().length).toBeGreaterThan(0);
    expect(component.activeModels()[0].model_name).toBe('BGE-M3');
  });

  it('should show Pause button for ready models', () => {
    const pauseBtn = fixture.debugElement.query(By.css('button[matTooltip*="Pause"]'));
    expect(pauseBtn).toBeTruthy();
    expect(pauseBtn.nativeElement.textContent).toContain('Pause');
  });

  it('should show Resume button for paused models', () => {
    component.summaries.set([{
      task_type: 'embedding',
      active_model: { id: 1, model_name: 'M', status: 'ready', task_type: 'embedding', role: 'champion' },
      candidates: [],
      master_paused: true
    } as any]);
    fixture.detectChanges();

    const resumeBtn = fixture.debugElement.query(By.css('button[matTooltip*="Resume"]'));
    expect(resumeBtn).toBeTruthy();
    expect(resumeBtn.nativeElement.textContent).toContain('Resume');
  });

  it('should call pause action and show snackbar', () => {
    svcSpy.action.and.returnValue(of({}));
    const model = component.activeModels()[0];
    component.pause(model);

    expect(svcSpy.action).toHaveBeenCalledWith(model.id, 'pause');
    expect(snackSpy.open).toHaveBeenCalledWith(jasmine.stringMatching(/Action "pause" applied/), jasmine.any(String), jasmine.any(Object));
  });

  it('should handle action error with snackbar', () => {
    svcSpy.action.and.returnValue(throwError(() => new Error('fail')));
    const model = component.activeModels()[0];
    component.pause(model);

    expect(snackSpy.open).toHaveBeenCalledWith(jasmine.stringMatching(/Failed to pause/), jasmine.any(String), jasmine.any(Object));
  });

  it('should show Promote button only for non-champions', () => {
    component.summaries.set([{
      task_type: 'embedding',
      active_model: { id: 2, model_name: 'C', status: 'ready', task_type: 'embedding', role: 'candidate' },
      candidates: [],
      master_paused: false
    } as any]);
    fixture.detectChanges();

    const promoteBtn = fixture.debugElement.query(By.css('button[matTooltip*="Promote"]'));
    expect(promoteBtn).toBeTruthy();
  });
});
