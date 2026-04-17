import {
  AfterViewInit,
  Directive,
  ElementRef,
  Input,
  OnDestroy,
  Renderer2,
  inject,
} from '@angular/core';

/**
 * Phase GK2 / Gap 230 — Column freezing in wide MatTables.
 *
 * Attach to a `<table mat-table>` and pass the column names to pin:
 *
 *   <table mat-table [appColumnFreeze]="['id', 'title']">
 *     ...
 *   </table>
 *
 * Applies `position: sticky` + accumulated `left` offset to every cell
 * in each pinned column (`td.mat-mdc-cell` and `th.mat-mdc-header-cell`
 * matching `.cdk-column-<name>`). The sum of offsets is recomputed
 * after view init + whenever the table's resize observer fires, so
 * columns stay pinned even when the operator resizes earlier columns.
 */
@Directive({
  selector: '[appColumnFreeze]',
  standalone: true,
})
export class ColumnFreezeDirective implements AfterViewInit, OnDestroy {
  @Input('appColumnFreeze') columns: string[] = [];

  private host = inject<ElementRef<HTMLElement>>(ElementRef);
  private renderer = inject(Renderer2);
  private resizeObserver: ResizeObserver | null = null;

  ngAfterViewInit(): void {
    // Re-compute on any host-size change (column resize, viewport shift).
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.apply());
      this.resizeObserver.observe(this.host.nativeElement);
    }
    // First pass after Angular has projected the header + rows.
    queueMicrotask(() => this.apply());
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
  }

  private apply(): void {
    const table = this.host.nativeElement;
    let offset = 0;
    for (const col of this.columns) {
      const cellClass = `.cdk-column-${col}`;
      const cells = table.querySelectorAll<HTMLElement>(cellClass);
      if (cells.length === 0) continue;
      // Width from the header cell is the authoritative column width.
      const header = table.querySelector<HTMLElement>(`th${cellClass}`);
      const width = header?.offsetWidth ?? cells[0].offsetWidth;
      for (const cell of Array.from(cells)) {
        this.renderer.setStyle(cell, 'position', 'sticky');
        this.renderer.setStyle(cell, 'left', `${offset}px`);
        this.renderer.setStyle(cell, 'z-index', '2');
        this.renderer.setStyle(
          cell,
          'background',
          'var(--color-bg, #ffffff)',
        );
        this.renderer.addClass(cell, 'column-frozen');
      }
      offset += width;
    }
  }
}
