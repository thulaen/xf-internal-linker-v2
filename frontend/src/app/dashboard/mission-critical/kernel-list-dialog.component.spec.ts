import { ComponentFixture, TestBed } from '@angular/core/testing';
import { KernelListDialogComponent, KernelDialogData } from './kernel-list-dialog.component';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

describe('KernelListDialogComponent', () => {
  let component: KernelListDialogComponent;
  let fixture: ComponentFixture<KernelListDialogComponent>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<KernelListDialogComponent>>;
  let mockData: KernelDialogData;

  beforeEach(async () => {
    mockDialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);
    mockData = {
      kernels: ['kernel_1', 'kernel_2', 'kernel_3'],
      tileState: 'ok'
    };

    await TestBed.configureTestingModule({
      imports: [
        KernelListDialogComponent,
        MatDialogModule,
        MatListModule,
        MatIconModule,
        NoopAnimationsModule
      ],
      providers: [
        { provide: MatDialogRef, useValue: mockDialogRef },
        { provide: MAT_DIALOG_DATA, useValue: mockData }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(KernelListDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display kernel count in title', () => {
    const title = fixture.nativeElement.querySelector('[mat-dialog-title]');
    expect(title.textContent).toContain('C++ Kernels (3)');
  });

  it('should list all kernels', () => {
    const items = fixture.nativeElement.querySelectorAll('mat-list-item');
    expect(items.length).toBe(3);
    expect(items[0].textContent).toContain('kernel_1');
    expect(items[1].textContent).toContain('kernel_2');
    expect(items[2].textContent).toContain('kernel_3');
  });

  it('should close when Close button is clicked', () => {
    const closeBtn = fixture.nativeElement.querySelector('button');
    closeBtn.click();
    expect(mockDialogRef.close).toHaveBeenCalled();
  });
});
