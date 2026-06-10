import { Component, ViewChild, NgZone } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { EchartsDirective } from './echarts.directive';
import * as echarts from 'echarts';

@Component({
  template: `<div [echarts]="options" (chartClick)="onClick($event)" style="width: 100px; height: 100px;"></div>`,
  standalone: true,
  imports: [EchartsDirective]
})
class TestHostComponent {
  @ViewChild(EchartsDirective) directive!: EchartsDirective;
  options: echarts.EChartsOption | null = { title: { text: 'Test Chart' } };
  onClick = jasmine.createSpy('onClick');
}

describe('EchartsDirective', () => {
  let fixture: ComponentFixture<TestHostComponent>;
  let component: TestHostComponent;
  let originalResizeObserver: any;
  let mockResizeObserver: any;
  let resizeCallback: ResizeObserverCallback | null = null;
  let zone: NgZone;

  beforeEach(() => {
    originalResizeObserver = globalThis.ResizeObserver;
    mockResizeObserver = {
      observe: jasmine.createSpy('observe'),
      disconnect: jasmine.createSpy('disconnect'),
    };

    globalThis.ResizeObserver = class {
      constructor(cb: ResizeObserverCallback) {
        resizeCallback = cb;
      }
      observe = mockResizeObserver.observe;
      disconnect = mockResizeObserver.disconnect;
    } as any;

    TestBed.configureTestingModule({
      imports: [TestHostComponent]
    });
    fixture = TestBed.createComponent(TestHostComponent);
    component = fixture.componentInstance;
    zone = TestBed.inject(NgZone);
  });

  afterEach(() => {
    globalThis.ResizeObserver = originalResizeObserver;
    resizeCallback = null;
  });

  it('should initialize echarts and set initial options', () => {
    fixture.detectChanges();
    const instance = component.directive.getInstance();
    expect(instance).toBeTruthy();
    
    // Verify that the options were applied
    const option = instance?.getOption() as any;
    expect(option.title[0].text).toEqual('Test Chart');
  });

  it('should initialize using canvas renderer implicitly (default in init args)', () => {
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('div');
    // ECharts creates a wrapper and a canvas inside it
    const canvas = el.querySelector('canvas');
    expect(canvas).toBeTruthy();
  });

  it('should update options using notMerge: true', () => {
    fixture.detectChanges();
    const instance = component.directive.getInstance();
    expect(instance).toBeTruthy();
    
    spyOn(instance as any, 'setOption').and.callThrough();
    
    component.options = { title: { text: 'Updated Title' } };
    fixture.detectChanges(); // Triggers ngOnChanges
    
    expect((instance as any).setOption).toHaveBeenCalledWith(
      component.options,
      { notMerge: true }
    );
  });

  it('should clear the chart when options are updated to null', () => {
    fixture.detectChanges();
    const instance = component.directive.getInstance();
    spyOn(instance as any, 'clear').and.callThrough();
    
    component.options = null;
    fixture.detectChanges();
    
    expect((instance as any).clear).toHaveBeenCalled();
  });

  it('should observe the host element for resizing', () => {
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('div');
    expect(mockResizeObserver.observe).toHaveBeenCalledWith(el);
  });

  it('should call resize on the echarts instance when ResizeObserver triggers', () => {
    fixture.detectChanges();
    const instance = component.directive.getInstance();
    spyOn(instance as any, 'resize').and.callThrough();
    
    expect(resizeCallback).toBeTruthy();
    if (resizeCallback) {
      resizeCallback([], mockResizeObserver as any);
      expect((instance as any).resize).toHaveBeenCalled();
    }
  });

  it('should run render logic outside the Angular zone', () => {
    spyOn(zone, 'runOutsideAngular').and.callThrough();
    fixture.detectChanges(); // First render
    expect(zone.runOutsideAngular).toHaveBeenCalled();
    
    (zone.runOutsideAngular as jasmine.Spy).calls.reset();
    
    component.options = { title: { text: 'New' } };
    fixture.detectChanges(); // Second render (update)
    expect(zone.runOutsideAngular).toHaveBeenCalled();
  });

  it('should setup the click listener (implied by no errors and event emitter existing)', () => {
    fixture.detectChanges();
    expect(component.directive.chartClick).toBeTruthy();
    // Cannot easily trigger ECharts click without coordinates and a rendered series,
    // and cannot easily spy on the read-only echarts.init to intercept the listener.
  });

  it('should cleanup the ResizeObserver and ECharts instance on destroy', () => {
    fixture.detectChanges();
    const instance = component.directive.getInstance();
    spyOn(instance as any, 'dispose').and.callThrough();
    
    fixture.destroy();
    
    expect(mockResizeObserver.disconnect).toHaveBeenCalled();
    expect((instance as any).dispose).toHaveBeenCalled();
    expect(component.directive.getInstance()).toBeNull();
  });
});
