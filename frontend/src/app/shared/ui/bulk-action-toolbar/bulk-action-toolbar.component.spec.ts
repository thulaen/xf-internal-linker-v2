import { ComponentFixture, TestBed } from '@angular/core/testing';
import { BulkActionToolbarComponent } from './bulk-action-toolbar.component';
import { Component } from '@angular/core';
import { By } from '@angular/platform-browser';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  template: `
    <app-bulk-action-toolbar [count]="selectedCount" (clearSelection)="onClear()">
      <button id="test-action">Action</button>
    </app-bulk-action-toolbar>
  `,
  standalone: true,
  imports: [BulkActionToolbarComponent]
})
class TestHostComponent {
  selectedCount = 0;
  onClear() {}
}

describe('BulkActionToolbarComponent', () => {
  let hostComponent: TestHostComponent;
  let fixture: ComponentFixture<TestHostComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestHostComponent, BulkActionToolbarComponent, MatButtonModule, MatIconModule],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHostComponent);
    hostComponent = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should not render when count is 0', () => {
    hostComponent.selectedCount = 0;
    fixture.detectChanges();
    const toolbar = fixture.debugElement.query(By.css('.bat'));
    expect(toolbar).toBeNull();
  });

  it('should render when count > 0', () => {
    hostComponent.selectedCount = 1;
    fixture.detectChanges();
    const toolbar = fixture.debugElement.query(By.css('.bat'));
    expect(toolbar).toBeTruthy();
    expect(toolbar.nativeElement.getAttribute('role')).toBe('toolbar');
  });

  it('should display correct count and pluralization', () => {
    hostComponent.selectedCount = 1;
    fixture.detectChanges();
    let countText = fixture.debugElement.query(By.css('.bat-count')).nativeElement.textContent;
    expect(countText).toContain('1 item selected');

    hostComponent.selectedCount = 5;
    fixture.detectChanges();
    countText = fixture.debugElement.query(By.css('.bat-count')).nativeElement.textContent;
    expect(countText).toContain('5 items selected');
  });

  it('should project content', () => {
    hostComponent.selectedCount = 1;
    fixture.detectChanges();
    const actionBtn = fixture.debugElement.query(By.css('#test-action'));
    expect(actionBtn).toBeTruthy();
    expect(actionBtn.nativeElement.textContent).toBe('Action');
  });

  it('should emit clearSelection when Clear button clicked', () => {
    hostComponent.selectedCount = 1;
    fixture.detectChanges();
    vi.spyOn(hostComponent, 'onClear').mockReturnValue(undefined as never);
    const clearBtn = fixture.debugElement.query(By.css('.bat-clear'));
    clearBtn.nativeElement.click();
    expect(hostComponent.onClear).toHaveBeenCalled();
  });
});
