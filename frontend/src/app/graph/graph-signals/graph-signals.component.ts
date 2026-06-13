import { Component, OnInit, ElementRef, ViewChild, HostListener, inject, OnDestroy } from '@angular/core';

import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { GraphService, GraphSignalsResponse } from '../graph.service';
import * as echarts from 'echarts';
import { Subject, takeUntil } from 'rxjs';

@Component({
  selector: 'app-graph-signals',
  standalone: true,
  imports: [MatCardModule, MatProgressSpinnerModule, MatIconModule, MatButtonModule, MatTooltipModule],
  templateUrl: './graph-signals.component.html',
  styleUrls: ['./graph-signals.component.scss'],
})
export class GraphSignalsComponent implements OnInit, OnDestroy {
  @ViewChild('chartContainer', { static: false }) chartContainer!: ElementRef;

  private graphService = inject(GraphService);
  private destroy$ = new Subject<void>();
  private chartInstance: echarts.ECharts | null = null;

  isLoading = true;
  runExists = false;
  data: GraphSignalsResponse | null = null;

  ngOnInit(): void {
    this.loadData();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    if (this.chartInstance) {
      this.chartInstance.dispose();
    }
  }

  @HostListener('window:resize')
  onResize(): void {
    if (this.chartInstance) {
      this.chartInstance.resize();
    }
  }

  loadData(): void {
    this.isLoading = true;
    this.graphService
      .getGraphSignals(200)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (res) => {
          this.data = res;
          this.runExists = res.run_exists;
          this.isLoading = false;
          if (this.runExists && res.nodes && res.links) {
            setTimeout(() => this.renderChart(), 0);
          }
        },
        error: () => {
          this.isLoading = false;
          this.runExists = false;
        },
      });
  }

  private renderChart(): void {
    if (!this.chartContainer) return;

    if (!this.chartInstance) {
      this.chartInstance = echarts.init(this.chartContainer.nativeElement);
    }

    const nodes = this.data?.nodes || [];
    const links = this.data?.links || [];

    const chartNodes = nodes.map((n) => {
      const size = n.betweenness
        ? Math.max(10, Math.min(40, n.betweenness * 100))
        : n.core_number
          ? Math.max(10, n.core_number * 5)
          : 10;
      return {
        id: n.id.toString(),
        name: n.title,
        symbolSize: size,
        value: n.community_id || 0,
        category: n.community_id ? `Community ${n.community_id}` : 'Unassigned',
        itemStyle: {
          color: this.getColorForCommunity(n.community_id),
        },
      };
    });

    const chartLinks = links.map((l) => ({
      source: l.source.toString(),
      target: l.target.toString(),
      value: l.adamic_adar || 1,
      lineStyle: {
        width: l.adamic_adar ? Math.max(1, l.adamic_adar) : 1,
        color: l.is_bridge ? '#e74c3c' : l.same_community ? '#3498db' : '#95a5a6',
        type: (l.is_bridge ? 'dashed' : 'solid') as 'solid' | 'dashed' | 'dotted',
      },
    }));

    const categories = Array.from(new Set(chartNodes.map((n) => n.category))).map((name) => ({ name }));

    const option: echarts.EChartsOption = {
      title: {
        text: 'Structural Link Candidates',
        subtext: 'NetworKit graph signals with Adamic-Adar predictions',
        top: 'bottom',
        left: 'right',
      },
      tooltip: {
        formatter: (params: unknown) => {
          const p = params as Record<string, unknown>;
          if (p['dataType'] === 'node') {
            const data = p['data'] as Record<string, unknown>;
            return `<b>${data['name']}</b><br/>Community: ${data['value']}`;
          } else if (p['dataType'] === 'edge') {
            const data = p['data'] as Record<string, unknown>;
            return `Adamic-Adar: ${(data['value'] as number).toFixed(3)}`;
          }
          return '';
        },
      },
      legend: [
        {
          data: categories.map((a) => a.name),
          type: 'scroll',
          orient: 'vertical',
          left: 10,
          top: 20,
          bottom: 20,
        },
      ],
      animationDuration: 1500,
      animationEasingUpdate: 'quinticInOut',
      series: [
        {
          name: 'Graph Signals',
          type: 'graph',
          layout: 'force',
          data: chartNodes,
          links: chartLinks,
          categories: categories,
          roam: true,
          label: {
            position: 'right',
            formatter: '{b}',
          },
          force: {
            repulsion: 300,
            edgeLength: 100,
          },
          lineStyle: {
            color: 'source',
            curveness: 0.3,
          },
          emphasis: {
            focus: 'adjacency',
            lineStyle: {
              width: 5,
            },
          },
        },
      ],
    };

    this.chartInstance.setOption(option);
  }

  private getColorForCommunity(communityId: number | null): string {
    if (communityId === null) return '#bdc3c7';
    const hue = (communityId * 137.508) % 360;
    return `hsl(${hue}, 70%, 50%)`;
  }
}
