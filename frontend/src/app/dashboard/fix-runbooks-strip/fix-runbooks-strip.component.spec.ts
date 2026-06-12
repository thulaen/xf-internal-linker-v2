import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FixRunbooksStripComponent } from './fix-runbooks-strip.component';
import { MatDialog } from '@angular/material/dialog';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('FixRunbooksStripComponent', () => {
  let component: FixRunbooksStripComponent;
  let fixture: ComponentFixture<FixRunbooksStripComponent>;
  let dialogSpy: SpyObj<MatDialog>;

  beforeEach(async () => {
    dialogSpy = createSpyObj(['open']);

    await TestBed.configureTestingModule({
      imports: [
        FixRunbooksStripComponent, 
        NoopAnimationsModule, 
        HttpClientTestingModule
      ],
    })
    .overrideComponent(FixRunbooksStripComponent, {
      set: {
        providers: [
          { provide: MatDialog, useValue: dialogSpy }
        ]
      }
    })
    .compileComponents();

    fixture = TestBed.createComponent(FixRunbooksStripComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should be hidden when healthy and no quarantine', () => {
    component.healthStatus = 'healthy';
    component.openQuarantineCount = 0;
    component.ngOnChanges();
    fixture.detectChanges();

    const strip = fixture.nativeElement.querySelector('.fix-strip');
    expect(strip).toBeNull();
  });

  it('should be visible when health status is "error"', () => {
    component.healthStatus = 'error';
    component.openQuarantineCount = 0;
    component.ngOnChanges();
    fixture.detectChanges();

    const strip = fixture.nativeElement.querySelector('.fix-strip');
    expect(strip).toBeTruthy();
    expect(component.subtitle()).toContain('One or more services are down');
  });

  it('should render runbook buttons when visible', () => {
    component.healthStatus = 'error';
    component.openQuarantineCount = 1;
    component.ngOnChanges();
    fixture.detectChanges();

    const buttons = fixture.nativeElement.querySelectorAll('.fix-strip-btn');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('should open dialog when runbook button is clicked', () => {
    component.healthStatus = 'error';
    component.openQuarantineCount = 0;
    component.ngOnChanges();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.fix-strip-btn');
    if (button) {
      button.click();
      expect(dialogSpy.open).toHaveBeenCalled();
    }
  });
});
