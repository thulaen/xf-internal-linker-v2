import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { QuickControlsComponent } from './quick-controls.component';
import { RuntimeModelsService } from '../../admin-models/runtime-models.service';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError, delay } from 'rxjs';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

describe('QuickControlsComponent', () => {
  let component: QuickControlsComponent;
  let fixture: ComponentFixture<QuickControlsComponent>;
  let svcSpy: SpyObj<RuntimeModelsService>;
  let snackOpenSpy: Spy;

  beforeEach(async () => {
    svcSpy = createSpyObj(['list', 'action']);

    svcSpy.list.mockReturnValue(of({
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
        provideRouter([])
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(QuickControlsComponent);
    component = fixture.componentInstance;
    snackOpenSpy = vi.spyOn(MatSnackBar.prototype, 'open').mockImplementation(() => null as any);
    fixture.detectChanges();
  });

  it('should create and render the card', () => {
    expect(component).toBeTruthy();
    const card = fixture.debugElement.query(By.css('mat-card'));
    expect(card).toBeTruthy();
  });

  it('should display loading spinner initially', () => {
    component.loading.set(true);
    fixture.detectChanges();
    const spinner = fixture.debugElement.query(By.css('mat-spinner'));
    expect(spinner).toBeTruthy();
  });

  it('should display error when no models found', fakeAsync(() => {
    component.error.set('No active model services found.');
    fixture.detectChanges();
    tick();

    const errorDiv = fixture.debugElement.query(By.css('.quick-error'));
    expect(errorDiv).toBeTruthy();
    expect(errorDiv.nativeElement.textContent).toContain('No active model');
  }));

  it('should list and display active models on init', () => {
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

  it('should call pause action and show success snackbar', fakeAsync(() => {
    svcSpy.action.mockReturnValue(of({ status: 'ok' }));
    const model = component.activeModels()[0];
    component.pause(model);
    tick(0);

    expect(svcSpy.action).toHaveBeenCalledWith(model.id, 'pause');
    expect(snackOpenSpy).toHaveBeenCalledWith(
      expect.stringMatching(/Action "pause" applied/),
      expect.any(String),
      expect.any(Object)
    );
  }));

  it('should handle action error with error snackbar', fakeAsync(() => {
    svcSpy.action.mockReturnValue(throwError(() => new Error('fail')));
    const model = component.activeModels()[0];
    component.pause(model);
    tick(0);

    expect(snackOpenSpy).toHaveBeenCalledWith(
      expect.stringMatching(/Failed to pause/),
      expect.any(String),
      expect.any(Object)
    );
  }));

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

  it('should set busy state during action execution', fakeAsync(() => {
    // Use a delayed observable so the subscription doesn't complete synchronously
    svcSpy.action.mockReturnValue(of({ status: 'ok' }).pipe(delay(1)));
    const models = component.activeModels();
    expect(models.length).toBeGreaterThan(0);
    const model = models[0];

    expect(component.busyId()).toBe('');
    component.resume(model);
    // Signal is set synchronously in runAction before subscribe
    expect(component.busyId()).toBe(`${model.id}:resume`);

    // Tick to process the observable subscription and complete handler
    tick(1);
    expect(component.busyId()).toBe('');
  }));

  it('should disable action buttons when busy', fakeAsync(() => {
    // Use a delayed observable so the subscription doesn't complete synchronously
    svcSpy.action.mockReturnValue(of({ status: 'ok' }).pipe(delay(1)));
    const model = component.activeModels()[0];

    component.pause(model);
    // Signal is set synchronously in runAction before subscribe
    expect(component.isBusy(model.id, 'pause')).toBe(true);
    expect(component.isBusy(model.id, 'resume')).toBe(false);

    // Tick to process the observable subscription and complete handler
    tick(1);
    expect(component.isBusy(model.id, 'pause')).toBe(false);
  }));

  it('should call drain action on drain button click', fakeAsync(() => {
    svcSpy.action.mockReturnValue(of({ status: 'ok' }));
    const model = component.activeModels()[0];

    component.drain(model);

    expect(svcSpy.action).toHaveBeenCalledWith(model.id, 'drain');
    tick(0);
  }));

  it('should refresh models after action completes', fakeAsync(() => {
    svcSpy.action.mockReturnValue(of({ status: 'ok' }));
    const initialListCallCount = svcSpy.list.mock.calls.length;
    const model = component.activeModels()[0];

    component.pause(model);
    tick(0);

    expect(svcSpy.list.mock.calls.length).toBeGreaterThan(initialListCallCount);
  }));
});
