import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  SimpleChanges,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import * as d3 from 'd3';

import { GraphLink, GraphNode, GraphTopology } from '../graph.service';

// D3 simulation node type — extends GraphNode with x/y/fx/fy fields.
interface SimNode extends GraphNode {
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

// D3 simulation link type — source/target become SimNode references after init.
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  context: string;
  weight: number;
}

/** Max radius a node can reach (px). */
const MAX_RADIUS = 20;
/** Base radius for a zero-pagerank node (px). */
const MIN_RADIUS = 4;

@Component({
  selector: 'app-link-graph-viz',
  standalone: true,
  imports: [CommonModule, MatProgressSpinnerModule],
  templateUrl: './link-graph-viz.component.html',
  styleUrls: ['./link-graph-viz.component.scss'],
})
export class LinkGraphVizComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() topology: GraphTopology = { nodes: [], links: [] };
  @Input() heatmapMode = false;
  @Input() prMin = 0;
  @Input() prMax = 1;
  @Output() nodeSelected = new EventEmitter<GraphNode | null>();

  @ViewChild('svgContainer') svgRef!: ElementRef<SVGSVGElement>;
  @ViewChild('wrapper') wrapperRef!: ElementRef<HTMLDivElement>;
  @ViewChild('tooltip') tooltipRef!: ElementRef<HTMLDivElement>;

  isSimulating = false;

  private simulation: d3.Simulation<SimNode, SimLink> | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private viewReady = false;
  private zoomBehavior: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null;
  private simNodes: SimNode[] = [];
  private _siloColor: d3.ScaleOrdinal<number, string> | null = null;
  private _orphanColor = '';

  ngAfterViewInit(): void {
    this.viewReady = true;
    this._setupResizeObserver();
    if (this.topology.nodes.length > 0) {
      this._buildGraph();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['topology'] && this.viewReady) {
      this._buildGraph();
    } else if ((changes['heatmapMode'] || changes['prMin'] || changes['prMax']) && this.viewReady) {
      this._applyColorMode();
    }
  }

  ngOnDestroy(): void {
    this.simulation?.stop();
    this.resizeObserver?.disconnect();
  }

  // ── Internal ──────────────────────────────────────────────────────────────

  private _setupResizeObserver(): void {
    this.resizeObserver = new ResizeObserver(() => {
      if (this.simulation) {
        const { width, height } = this._dims();
        this.simulation.force('center', d3.forceCenter(width / 2, height / 2));
        this.simulation.alpha(0.1).restart();
      }
    });
    this.resizeObserver.observe(this.wrapperRef.nativeElement);
  }

  private _dims(): { width: number; height: number } {
    const el = this.wrapperRef.nativeElement;
    return { width: el.clientWidth || 800, height: el.clientHeight || 560 };
  }

  private _nodeRadius(node: SimNode): number {
    const r = Math.log(node.pagerank * 100 + 1) * 3 + MIN_RADIUS;
    return Math.min(r, MAX_RADIUS);
  }

  private _buildGraph(): void {
    this.simulation?.stop();

    const svgEl = this.svgRef.nativeElement;
    d3.select(svgEl).selectAll('*').remove();

    const { nodes, links } = this.topology;
    if (nodes.length === 0) return;

    const { width, height } = this._dims();

    // Deep-clone so D3 mutation doesn't affect the original input.
    this.simNodes = nodes.map((n) => ({ ...n }));
    const simNodes = this.simNodes;
    const simLinks: SimLink[] = links.map((l) => ({
      source: l.source as unknown as SimNode,
      target: l.target as unknown as SimNode,
      context: l.context,
      weight: l.weight,
    }));

    // Build a map for quick neighbor lookup during hover.
    const neighborSet = new Map<number, Set<number>>();
    for (const l of links) {
      if (!neighborSet.has(l.source)) neighborSet.set(l.source, new Set());
      if (!neighborSet.has(l.target)) neighborSet.set(l.target, new Set());
      neighborSet.get(l.source)!.add(l.target);
      neighborSet.get(l.target)!.add(l.source);
    }

    // Colour scale — one colour per unique silo_id.
    const siloIds = [...new Set(simNodes.map((n) => n.silo_id))];
    const color = d3.scaleOrdinal<number, string>(d3.schemeTableau10).domain(siloIds);
    this._siloColor = color;

    // Orphan nodes use the error/danger colour from the theme.
    const orphanColor = getComputedStyle(document.documentElement)
      .getPropertyValue('--graph-node-orphan').trim();
    this._orphanColor = orphanColor;

    // ── SVG setup ────────────────────────────────────────────────────────────

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height);

    // Zoom/pan container.
    const container = svg.append('g').attr('class', 'graph-container');

    this.zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 8])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });
    svg.call(this.zoomBehavior);

    // ── Force simulation ──────────────────────────────────────────────────────

    this.simulation = d3.forceSimulation<SimNode, SimLink>(simNodes)
      .force('link', d3.forceLink<SimNode, SimLink>(simLinks)
        .id((d) => d.id)
        .strength((l) => l.weight * 0.3)
      )
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide<SimNode>().radius((d) => this._nodeRadius(d) + 2));

    // ── Edges ─────────────────────────────────────────────────────────────────

    const link = container.append('g')
      .attr('class', 'links')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(simLinks)
      .join('line')
      .attr('class', 'edge')
      .attr('stroke-opacity', 0.4);

    // ── Nodes ─────────────────────────────────────────────────────────────────

    const nodeGroup = container.append('g')
      .attr('class', 'nodes')
      .selectAll<SVGCircleElement, SimNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('class', 'node')
      .attr('r', (d) => this._nodeRadius(d))
      .attr('fill', (d) => this._nodeColor(d))
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .call(this._drag(this.simulation))
      .on('mouseover', (event, d) => this._onHover(event, d, nodeGroup, link, neighborSet))
      .on('mouseout', () => this._onHoverEnd(nodeGroup, link))
      .on('click', (event, d) => {
        event.stopPropagation();
        this.nodeSelected.emit(d);
      });

    // Click on empty canvas deselects.
    svg.on('click', () => this.nodeSelected.emit(null));

    // ── Tick ──────────────────────────────────────────────────────────────────

    const isLarge = simNodes.length > 500;

    if (isLarge) {
      // Pre-compute layout without live rendering to keep the UI responsive.
      this.isSimulating = true;
      this.simulation.stop();

      const TICKS = 300;
      let tick = 0;
      const step = () => {
        if (tick < TICKS) {
          this.simulation!.tick();
          tick++;
          requestAnimationFrame(step);
        } else {
          this.isSimulating = false;
          this._applyPositions(nodeGroup, link);
        }
      };
      requestAnimationFrame(step);
    } else {
      this.simulation.on('tick', () => this._applyPositions(nodeGroup, link));
    }

    this._renderLegend(svg, width, height);
  }

  private _applyPositions(
    nodeGroup: d3.Selection<SVGCircleElement, SimNode, SVGGElement, unknown>,
    link: d3.Selection<SVGLineElement, SimLink, SVGGElement, unknown>
  ): void {
    link
      .attr('x1', (d) => (d.source as SimNode).x ?? 0)
      .attr('y1', (d) => (d.source as SimNode).y ?? 0)
      .attr('x2', (d) => (d.target as SimNode).x ?? 0)
      .attr('y2', (d) => (d.target as SimNode).y ?? 0);

    nodeGroup
      .attr('cx', (d) => d.x ?? 0)
      .attr('cy', (d) => d.y ?? 0);
  }

  private _drag(sim: d3.Simulation<SimNode, SimLink>): d3.DragBehavior<SVGCircleElement, SimNode, SimNode | d3.SubjectPosition> {
    return d3.drag<SVGCircleElement, SimNode>()
      .on('start', (event, d) => {
        if (!event.active) sim.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event) => {
        if (!event.active) sim.alphaTarget(0);
        // Leave fx/fy set — node stays pinned where the user dropped it.
      });
  }

  private _nodeColor(d: SimNode): string {
    if (this.heatmapMode) {
      const lo = this.prMin > 0 ? this.prMin : 1e-9;
      const hi = this.prMax > lo ? this.prMax : lo * 10;
      const scale = d3.scaleLog<number>().domain([lo, hi]).range([0, 1]).clamp(true);
      return d3.interpolateRdYlBu(1 - scale(Math.max(d.pagerank, lo)));
    }
    return d.in_degree === 0
      ? this._orphanColor
      : (this._siloColor ? this._siloColor(d.silo_id) : '#aaa');
  }

  private _applyColorMode(): void {
    if (!this.svgRef?.nativeElement) return;
    d3.select(this.svgRef.nativeElement)
      .selectAll<SVGCircleElement, SimNode>('.node')
      .attr('fill', (d) => this._nodeColor(d));
    const { width, height } = this._dims();
    this._renderLegend(d3.select(this.svgRef.nativeElement), width, height);
  }

  private _renderLegend(
    svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
    width: number,
    height: number
  ): void {
    svg.select('.heatmap-legend').remove();
    svg.select('defs #heatmap-grad').remove();
    if (!this.heatmapMode) return;

    const BAR_W = 120, BAR_H = 10, M = 16;
    let defs = svg.select<SVGDefsElement>('defs');
    if (defs.empty()) defs = svg.append('defs') as d3.Selection<SVGDefsElement, unknown, null, undefined>;
    const grad = defs.append('linearGradient').attr('id', 'heatmap-grad');
    d3.range(0, 1.01, 0.1).forEach(t => {
      grad.append('stop')
        .attr('offset', `${Math.round(t * 100)}%`)
        .attr('stop-color', d3.interpolateRdYlBu(1 - t));
    });

    const g = svg.append('g')
      .attr('class', 'heatmap-legend')
      .attr('transform', `translate(${M}, ${height - M - BAR_H - 16})`);

    g.append('rect')
      .attr('width', BAR_W).attr('height', BAR_H).attr('rx', 2)
      .attr('fill', 'url(#heatmap-grad)');

    ([{ x: 0, anchor: 'start', label: 'Low' }, { x: BAR_W, anchor: 'end', label: 'High' }] as const)
      .forEach(({ x, anchor, label }) => {
        g.append('text')
          .attr('x', x).attr('y', BAR_H + 12)
          .attr('font-size', '10px')
          .attr('text-anchor', anchor)
          .attr('fill', 'var(--color-text-muted)')
          .text(label);
      });
  }

  private _onHover(
    event: MouseEvent,
    hovered: SimNode,
    nodeGroup: d3.Selection<SVGCircleElement, SimNode, SVGGElement, unknown>,
    link: d3.Selection<SVGLineElement, SimLink, SVGGElement, unknown>,
    neighborSet: Map<number, Set<number>>
  ): void {
    const neighbors = neighborSet.get(hovered.id) ?? new Set<number>();

    nodeGroup.attr('opacity', (d) =>
      d.id === hovered.id || neighbors.has(d.id) ? 1 : 0.15
    );
    link.attr('stroke-opacity', (l) => {
      const s = (l.source as SimNode).id;
      const t = (l.target as SimNode).id;
      return s === hovered.id || t === hovered.id ? 0.8 : 0.05;
    });

    // Tooltip
    const tooltip = d3.select(this.tooltipRef.nativeElement);
    tooltip
      .style('display', 'block')
      .style('left', `${event.offsetX + 12}px`)
      .style('top', `${event.offsetY - 10}px`)
      .html(
        `<strong>${hovered.title}</strong><br>` +
        `In: ${hovered.in_degree} &nbsp; Out: ${hovered.out_degree}<br>` +
        `Silo: ${hovered.silo_id}`
      );
  }

  private _onHoverEnd(
    nodeGroup: d3.Selection<SVGCircleElement, SimNode, SVGGElement, unknown>,
    link: d3.Selection<SVGLineElement, SimLink, SVGGElement, unknown>
  ): void {
    nodeGroup.attr('opacity', 1);
    link.attr('stroke-opacity', 0.4);
    d3.select(this.tooltipRef.nativeElement).style('display', 'none');
  }

  /**
   * Programmatically zoom to a node and select it.
   * Returns false if the node is not in the current topology.
   */
  focusNode(nodeId: number): boolean {
    const node = this.simNodes.find((n) => n.id === nodeId);
    if (!node || node.x == null || node.y == null) return false;

    this.nodeSelected.emit(node);

    const svgEl = this.svgRef?.nativeElement;
    if (!svgEl || !this.zoomBehavior) return false;

    const { width, height } = this._dims();
    const scale = 2;
    const transform = d3.zoomIdentity
      .translate(width / 2, height / 2)
      .scale(scale)
      .translate(-node.x, -node.y);

    d3.select(svgEl)
      .transition()
      .duration(750)
      .call(this.zoomBehavior.transform as any, transform);

    // Highlight the focused node with a thicker stroke.
    d3.select(svgEl)
      .selectAll<SVGCircleElement, SimNode>('.node')
      .attr('stroke-width', (d) => d.id === nodeId ? 3 : 1.5)
      .attr('stroke', (d) => d.id === nodeId ? 'var(--color-primary)' : '#fff');

    return true;
  }
}
