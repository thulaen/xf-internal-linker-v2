import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { RunPipelineDialogComponent } from './run-pipeline-dialog.component';
import { MatDialogRef } from '@angular/material/dialog';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { FormsModule } from '@angular/forms';

describe('RunPipelineDialogComponent', () => {
  let component: RunPipelineDialogComponent;
  let fixture: ComponentFixture<RunPipelineDialogComponent>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<RunPipelineDialogComponent>>;

  beforeEach(async () => {
    mockDialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [
        RunPipelineDialogComponent,
        NoopAnimationsModule,
        FormsModule
      ],
      providers: [
        { provide: MatDialogRef, useValue: mockDialogRef }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(RunPipelineDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have default selectedMode as skip_pending', () => {
    expect(component.selectedMode()).toBe('skip_pending');
  });

  it('should close with null when Cancel is clicked', fakeAsync(() => {
    fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('button');
    buttons[0].click();
    tick();
    expect(mockDialogRef.close).toHaveBeenCalledWith(null);
  }));

  it('should close with selectedMode when confirm is clicked', fakeAsync(() => {
    component.selectedMode.set('full_regenerate');
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('button');
    // Button index 1 is "Run" (index 0 is "Cancel")
    buttons[1].click();
    tick();

    expect(mockDialogRef.close).toHaveBeenCalledWith({ rerunMode: 'full_regenerate' });
  }));

  it('should update activeDescription when mode changes', () => {
    component.selectedMode.set('supersede_pending');
    expect(component.activeDescription).toContain('Replace all pending suggestions');
  });
});
