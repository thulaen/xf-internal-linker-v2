import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  NgZone,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
  inject,
  signal,
} from '@angular/core';

import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import * as echarts from 'echarts';

import { GhostEdge, GraphNode, GraphTopology } from '../graph.service';
import { token } from '../../shared/charts/echarts-theme';

/** Minimal shape of the ECharts click event we read (node/edge + data). */
interface ChartClickParams {
  dataType?: string;
  data?: Record<string, unknown>;
}

/** Max radius a node can reach (px). */
const MAX_RADIUS = 20;
/** Base radius for a zero-pagerank node (px). */
const MIN_RADIUS = 4;

/**
 * Tableau-10 categorical palette for silo colours. Matched to the d3
 * `schemeTableau10` ordinal scale the previous version used so the silo
 * colours stay recognisable across the migration.
 */
const SILO_PALETTE = [
  '#4e79a7',
  '#f28e2b',
  '#e15759',
  '#76b7b2',
  '#59a14f',
  '#edc949',
  '#af7aa1',
  '#ff9da7',
  '#9c755f',
  '#bab0ab',
];

/**
 * Link graph (Slice 15 / Phase 6) — Apache ECharts `graph` series with a
 * force layout. Replaces the hand-written d3 force simulation. Keeps the
 * same `@Input`/`@Output` contract and the imperative `focusNode()` helper
 * so the parent (`graph.component`) needs no changes beyond the host swap.
 *
 * Feature parity with the d3 version:
 *  - force layout, zoom + pan (`roam`), draggable nodes;
 *  - hover dims everything except the node and its neighbours
 *    (`emphasis.focus: 'adjacency'`);
 *  - silo colours via ECharts categories;
 *  - PageRank heat mode (RdYlBu-style ramp) toggled by `heatmapMode`;
 *  - churn rings drawn as a second graph series behind the nodes;
 *  - ghost-edge overlay (dashed potential links) as a third series;
 *  - context filter hides weak/isolated edges;
 *  - tooltip with title / degree / silo;
 *  - programmatic focus + zoom on a node id.
 */
@Component({
  selector: 'app-link-graph-viz',
  standalone: true,
  imports: [MatProgressSpinnerModule],
  templateUrl: './link-graph-viz.component.html',
  styleUrls: ['./link-graph-viz.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LinkGraphVizComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() topology: GraphTopology = { nodes: [], links: [], history: [], churny_ids: [], churny_nodes: [] };
  @Input() heatmapMode = false;
  @Input() prMin = 0;
  @Input() prMax = 1;
  @Input() contextFilter: 'all' | 'contextual' = 'all';
  @Input() highlightEdge: { source: number; target: number } | null = null;
  @Input() churnyIds: Set<number> = new Set();
  @Input() ghostEdges: GhostEdge[] = [];
  @Input() showGhostEdges = false;
  @Output() nodeSelected = new EventEmitter<GraphNode | null>();
  @Output() ghostEdgeClicked = new EventEmitter<GhostEdge>();

  @ViewChild('chartHost') chartHostRef!: ElementRef<HTMLDivElement>;
  @ViewChild('wrapper') wrapperRef!: ElementRef<HTMLDivElement>;

  /** Template-bound: drives the loading overlay while the layout settles. */
  readonly isSimulating = signal(false);

  private readonly zone = inject(NgZone);
  private chart: echarts.ECharts | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private viewReady = false;
  /** Index of node id → GraphNode for click/tooltip lookups. */
  private nodeById = new Map<number, GraphNode>();

  ngAfterViewInit(): void {
    this.viewReady = true;
    this.zone.runOutsideAngular(() => {
      this.chart = echarts.init(this.chartHostRef.nativeElement, undefined, { renderer: 'canvas' });
      this.chart.on('click', (params) => this.onChartClick(params as ChartClickParams));
      this.resizeObserver = new ResizeObserver(() => this.chart?.resize());
      this.resizeObserver.observe(this.wrapperRef.nativeElement);
    });
    if (this.topology.nodes.length > 0) {
      this.render();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.viewReady) return;
    // Any input that changes the picture re-builds the option. ECharts
    // diffs internally, so a full rebuild is simple and correct (KISS) —
    // the per-property d3 mutators are no longer needed.
    if (
      changes['topology'] ||
      changes['heatmapMode'] ||
      changes['prMin'] ||
      changes['prMax'] ||
      changes['contextFilter'] ||
      changes['highlightEdge'] ||
      changes['ghostEdges'] ||
      changes['showGhostEdges'] ||
      changes['churnyIds']
    ) {
      this.render();
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.chart?.dispose();
    this.chart = null;
  }

  // ── Internal ──────────────────────────────────────────────────────────────

  private nodeRadius(node: GraphNode): number {
    const r = Math.log(node.pagerank * 100 + 1) * 3 + MIN_RADIUS;
    return Math.min(r, MAX_RADIUS);
  }

  /** RdYlBu-style heat colour for a pagerank value (high = warm/red). */
  private heatColor(pagerank: number): string {
    const lo = this.prMin > 0 ? this.prMin : 1e-9;
    const hi = this.prMax > lo ? this.prMax : lo * 10;
    const span = Math.log(hi) - Math.log(lo);
    const t = span > 0 ? Math.min(1, Math.max(0, (Math.log(Math.max(pagerank, lo)) - Math.log(lo)) / span)) : 0;
    return rdYlBu(t);
  }

  private nodeColor(node: GraphNode): string {
    if (this.heatmapMode) {
      return this.heatColor(node.pagerank);
    }
    if (node.in_degree === 0) {
      return token('--graph-node-orphan');
    }
    return SILO_PALETTE[Math.abs(node.silo_id) % SILO_PALETTE.length];
  }

  private edgeColor(ctx: string): string {
    if (ctx === 'isolated') return token('--color-error');
    if (ctx === 'weak_context') return token('--color-warning-accent');
    return '#bdc1c6';
  }

  private render(): void {
    if (!this.chart) return;
    const { nodes, links } = this.topology;
    if (nodes.length === 0) {
      this.chart.clear();
      return;
    }

    this.nodeById = new Map(nodes.map((n) => [n.id, n]));

    // Large graphs take a moment to settle; show the overlay until the
    // force layout stabilises (`graphRoam`/`finished` event).
    const isLarge = nodes.length > 500;
    this.zone.run(() => this.isSimulating.set(isLarge));

    // One graph series holds every node and every edge so they share the
    // same force layout — the d3 version drew ghost edges and churn rings
    // off the same node positions, and a single series is the only way to
    // keep them aligned in ECharts. Churny pages get a dashed warning
    // border directly on the node (the old "ring" overlay) instead of a
    // separate misaligned series.
    const warning = token('--color-warning-accent');
    const graphNodes = nodes.map((n) => {
      const churny = this.churnyIds.has(n.id);
      return {
        id: String(n.id),
        name: n.title,
        symbolSize: this.nodeRadius(n) * 2,
        itemStyle: {
          color: this.nodeColor(n),
          borderColor: churny ? warning : '#fff',
          borderWidth: churny ? 3 : 1.5,
          borderType: (churny ? 'dashed' : 'solid') as 'dashed' | 'solid',
        },
        value: n.pagerank,
        _silo: n.silo_id,
        _in: n.in_degree,
        _out: n.out_degree,
      };
    });

    const visibleLinks = links.filter((l) => this.contextFilter !== 'contextual' || l.context === 'contextual');
    const graphLinks = visibleLinks.map((l) => {
      const highlighted =
        this.highlightEdge && l.source === this.highlightEdge.source && l.target === this.highlightEdge.target;
      return {
        source: String(l.source),
        target: String(l.target),
        lineStyle: {
          color: highlighted ? token('--color-primary') : this.edgeColor(l.context),
          opacity: highlighted ? 0.95 : 0.4,
          width: highlighted ? 2.5 : 1,
        },
      };
    });

    // Ghost edges: dashed "potential link" overlay between existing nodes,
    // added to the same series so they track real node positions.
    const ghostVisible = this.showGhostEdges
      ? this.ghostEdges.filter((g) => this.nodeById.has(g.source) && this.nodeById.has(g.target))
      : [];
    const ghostLinks = ghostVisible.map((g) => ({
      source: String(g.source),
      target: String(g.target),
      _ghost: g,
      lineStyle: {
        color: token('--color-primary'),
        opacity: 0.5,
        width: 1.5,
        type: 'dashed' as const,
      },
    }));

    const option: echarts.EChartsOption = {
      tooltip: {
        backgroundColor: 'rgba(32, 33, 36, 0.92)',
        borderWidth: 0,
        padding: 12,
        textStyle: { color: '#e8eaed', fontSize: 12 },
        formatter: (params) => graphTooltip(params as ChartClickParams),
      },
      legend: { show: false },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          force: { repulsion: 120, edgeLength: 80, gravity: 0.08 },
          emphasis: { focus: 'adjacency', lineStyle: { width: 2 } },
          lineStyle: { curveness: 0 },
          data: graphNodes,
          links: [...graphLinks, ...ghostLinks],
        },
      ],
    };

    this.chart.setOption(option, { notMerge: true });
    this.chart.off('finished');
    this.chart.on('finished', () => this.zone.run(() => this.isSimulating.set(false)));

    // Heat legend (low → high) for heatmap mode.
    if (this.heatmapMode) {
      this.applyHeatVisualMap();
    }
  }

  /** Add a visualMap legend showing the low→high PageRank colour ramp. */
  private applyHeatVisualMap(): void {
    if (!this.chart) return;
    this.chart.setOption({
      visualMap: {
        show: true,
        type: 'continuous',
        min: this.prMin,
        max: this.prMax > this.prMin ? this.prMax : this.prMin + 1,
        left: 16,
        bottom: 16,
        dimension: undefined,
        seriesIndex: [],
        text: ['High', 'Low'],
        calculable: false,
        inRange: { color: [rdYlBu(0), rdYlBu(0.5), rdYlBu(1)] },
        textStyle: { color: token('--color-text-muted'), fontSize: 10 },
        itemWidth: 12,
        itemHeight: 80,
      },
    });
  }

  private onChartClick(params: ChartClickParams): void {
    const data = params.data as Record<string, unknown> | undefined;
    if (params.dataType === 'edge' && data && data['_ghost']) {
      this.zone.run(() => this.ghostEdgeClicked.emit(data['_ghost'] as GhostEdge));
      return;
    }
    if (params.dataType === 'node' && data && typeof data['id'] === 'string') {
      const id = Number(data['id']);
      const node = this.nodeById.get(id);
      if (node) {
        this.zone.run(() => this.nodeSelected.emit(node));
        return;
      }
    }
    // Click on empty canvas deselects.
    this.zone.run(() => this.nodeSelected.emit(null));
  }

  /**
   * Programmatically focus a node: emit selection, highlight its adjacency,
   * and zoom toward it. Returns false if the node is not in the current
   * topology so the caller can fall back (e.g. show a "not on screen" hint).
   */
  focusNode(nodeId: number): boolean {
    const node = this.nodeById.get(nodeId);
    if (!node || !this.chart) return false;

    this.nodeSelected.emit(node);
    this.zone.runOutsideAngular(() => {
      this.chart?.dispatchAction({
        type: 'focusNodeAdjacency',
        seriesIndex: 0,
        dataIndex: [...this.nodeById.keys()].indexOf(nodeId),
      });
      // Zoom in toward the focused node (the single graph series).
      this.chart?.dispatchAction({ type: 'graphRoam', seriesIndex: 0, zoom: 1.5 });
    });
    return true;
  }
}

/** Build the hover tooltip HTML for a node or a ghost edge. */
function graphTooltip(p: ChartClickParams): string {
  const data = p.data;
  if (p.dataType === 'node' && data && typeof data['_in'] === 'number') {
    return (
      `<strong>${data['name']}</strong><br>` +
      `In: ${data['_in']} &nbsp; Out: ${data['_out']}<br>` +
      `Silo: ${data['_silo']}`
    );
  }
  if (p.dataType === 'edge' && data && data['_ghost']) {
    const g = data['_ghost'] as GhostEdge;
    return `<strong>Potential link</strong><br>"${g.anchor_phrase}"<br>Score: ${g.score_final.toFixed(2)}`;
  }
  return '';
}

/**
 * RdYlBu-style diverging ramp (blue → yellow → red) for `t` in [0, 1].
 * High `t` returns warm red (high PageRank), low `t` returns cool blue —
 * matching the d3 `interpolateRdYlBu(1 - t)` the previous version used.
 * Three-stop linear interpolation keeps it tiny and dependency-free.
 */
function rdYlBu(t: number): string {
  const clamped = Math.min(1, Math.max(0, t));
  const blue = [49, 54, 149];
  const yellow = [255, 255, 191];
  const red = [165, 0, 38];
  const [a, b, local] = clamped < 0.5 ? [blue, yellow, clamped / 0.5] : [yellow, red, (clamped - 0.5) / 0.5];
  const mix = (i: number) => Math.round(a[i] + (b[i] - a[i]) * local);
  return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
}
