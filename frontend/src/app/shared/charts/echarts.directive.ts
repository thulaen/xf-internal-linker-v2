import {
  Directive,
  ElementRef,
  EventEmitter,
  Input,
  NgZone,
  OnChanges,
  OnDestroy,
  Output,
  inject,
} from '@angular/core';
import * as echarts from 'echarts';

/**
 * Owned `[echarts]` directive (Slice 15 / Phase 6).
 *
 * Replaces ng2-charts' `baseChart` directive and the per-route
 * `provideCharts(...)` provider. The repo is migrating OFF third-party UI
 * libraries (Angular Material → CDK + Tailwind), so we own this thin wrapper
 * around Apache ECharts rather than re-introducing a community wrapper +
 * provider.
 *
 * Usage:
 *   <div class="chart-host" [echarts]="optionSignal()" (chartClick)="...">
 *
 * Responsibilities (and nothing more — KISS):
 *  - init the chart on the host element once the element has a size;
 *  - re-apply the option whenever the `echarts` input changes
 *    (`notMerge: true` so stale series are cleared — truthful states);
 *  - auto-resize with a ResizeObserver (replaces chart.js
 *    `responsive: true` + `maintainAspectRatio: false`);
 *  - run ECharts outside Angular's zone so its internal rAF loop does not
 *    trip change detection on every animation frame;
 *  - dispose the instance + observer on destroy (no leaks).
 */
@Directive({
  // eslint-disable-next-line @angular-eslint/directive-selector
  selector: '[echarts]',
  standalone: true,
})
export class EchartsDirective implements OnChanges, OnDestroy {
  /** The ECharts option object. `null`/`undefined` clears the chart. */
  @Input() echarts: echarts.EChartsOption | null = null;

  /** Emits the ECharts `click` param when a series item is clicked. */
  @Output() chartClick = new EventEmitter<unknown>();

  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly zone = inject(NgZone);
  private instance: echarts.ECharts | null = null;
  private resizeObserver: ResizeObserver | null = null;

  ngOnChanges(): void {
    this.zone.runOutsideAngular(() => this.render());
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.instance?.dispose();
    this.instance = null;
  }

  private render(): void {
    const el = this.host.nativeElement;
    if (!this.instance) {
      // Element may have zero size before layout settles; ECharts handles a
      // 0x0 init and the ResizeObserver paints it once the host gets a size.
      this.instance = echarts.init(el, undefined, { renderer: 'canvas' });
      this.instance.on('click', (params: unknown) =>
        this.zone.run(() => this.chartClick.emit(params)),
      );
      this.resizeObserver = new ResizeObserver(() => this.instance?.resize());
      this.resizeObserver.observe(el);
    }
    if (this.echarts) {
      this.instance.setOption(this.echarts, { notMerge: true });
    } else {
      this.instance.clear();
    }
  }

  /** Exposed for components that need imperative access (e.g. focus/zoom). */
  getInstance(): echarts.ECharts | null {
    return this.instance;
  }
}
