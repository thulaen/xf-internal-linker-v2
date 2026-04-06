import { Component, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { MatTabsModule } from '@angular/material/tabs';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { debounceTime, distinctUntilChanged, Subject, switchMap } from 'rxjs';
import { BaseChartDirective } from 'ng2-charts';
import { ChartData, ChartOptions } from 'chart.js';

import {
  GraphService,
  GraphStats,
  GraphNode,
  GraphLink,
  GraphTopology,
  HistoryPoint,
  ChurnNode,
  EntityNode,
  EntityType,
  ContentItemSummary,
  SiloGroupSummary,
  PathResult,
  PathNode,
  AuditMode,
  PageRankEquity,
} from './graph.service';
import { LinkGraphVizComponent } from './link-graph-viz/link-graph-viz.component';

// ── Qualities tab local types ─────────────────────────────────────────────────

interface PageQualityRow {
  id: number;
  title: string;
  inbound: number;
  contextual: number;
  contextualPct: number;
  qualityLabel: 'High' | 'Medium' | 'Low';
}

interface IsolatedLinkRow {
  source: number;
  srcTitle: string;
  target: number;
  tgtTitle: string;
  anchor: string;
}

interface AnchorWarning {
  anchor: string;
  count: number;
  pct: number;
}

@Component({
  selector: 'app-graph',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatTabsModule,
    MatCardModule,
    MatIconModule,
    MatTableModule,
    MatPaginatorModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
    MatAutocompleteModule,
    MatSelectModule,
    MatSnackBarModule,
    MatSlideToggleModule,
    LinkGraphVizComponent,
    BaseChartDirective,
  ],
  templateUrl: './graph.component.html',
  styleUrls: ['./graph.component.scss'],
})
export class GraphComponent implements OnInit {
  @ViewChild(LinkGraphVizComponent) private vizComponent?: LinkGraphVizComponent;

  selectedTabIndex = 0;

  // ── Tab 1: Overview ──────────────────────────────────────────────
  stats: GraphStats | null = null;
  loadingStats = false;

  // ── Tab 2: Topics ────────────────────────────────────────────────
  topics: SiloGroupSummary[] = [];
  loadingTopics = false;

  // ── Tab 3: Entities ──────────────────────────────────────────────
  entities: EntityNode[] = [];
  entityCount = 0;
  loadingEntities = false;
  entityTypeFilter: EntityType | '' = '';
  entitySearch = '';
  entityPage = 1;
  entityColumns = ['canonical_form', 'entity_type', 'article_count'];
  private entitySearchSubject = new Subject<string>();

  // ── Tab 4: Hub Articles ──────────────────────────────────────────
  hubArticles: ContentItemSummary[] = [];
  loadingHubs = false;
  hubColumns = ['title', 'content_type_label', 'march_2026_pagerank_score'];

  // ── Tab 5: Audits (Orphan & Low-Authority Pages) ─────────────────
  auditItems: ContentItemSummary[] = [];
  auditCount = 0;
  loadingAudit = false;
  auditPage = 1;
  auditPageSize = 50;
  auditMode: AuditMode = 'orphan';
  auditColumns = ['title', 'scope_title', 'inbound_link_count', 'march_2026_pagerank_score', 'actions'];
  suggestingId: number | null = null;

  // ── Tab 6: Network Visualization ────────────────────────────────
  topology: GraphTopology = { nodes: [], links: [], history: [], churny_ids: [], churny_nodes: [] };
  loadingTopology = false;
  selectedNode: GraphNode | null = null;
  selectedNodeLinks: { inbound: GraphLink[]; outbound: GraphLink[] } = { inbound: [], outbound: [] };
  heatmapMode = false;
  historyMode = false;
  historyDate = '';
  churnyIds: Set<number> = new Set();
  pageRankEquity: PageRankEquity | null = null;
  loadingEquity = false;
  readonly authorityColumns = ['rank', 'title', 'silo_name', 'in_degree', 'out_degree', 'pagerank'];
  readonly today = new Date().toISOString().slice(0, 10);

  // ── Tab 9: Freshness ─────────────────────────────────────────────
  velocityChartData: ChartData<'line'> | null = null;
  velocityChartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { position: 'top' } },
    scales: {
      x: { ticks: { maxTicksLimit: 15, font: { size: 11 } } },
      y: { stacked: false, beginAtZero: true, ticks: { precision: 0 } },
    },
  };
  churnTable: ChurnNode[] = [];
  loadingFreshness = false;
  readonly churnColumns = ['title', 'churn_count'];

  // ── Tab 6: Qualities ─────────────────────────────────────────────
  contextFilter: 'all' | 'contextual' = 'all';
  highlightEdge: { source: number; target: number } | null = null;
  contextPieData: ChartData<'pie'> | null = null;
  anchorBarData: ChartData<'bar'> | null = null;
  pageQualityRows: PageQualityRow[] = [];
  isolatedLinks: IsolatedLinkRow[] = [];
  anchorWarnings: AnchorWarning[] = [];
  readonly qualityColumns = ['title', 'inbound', 'contextualPct', 'qualityLabel'];
  readonly isolatedColumns = ['srcTitle', 'tgtTitle', 'anchor', 'jump'];

  // ── Tab 7: Path Explorer ─────────────────────────────────────────
  fromQuery = '';
  toQuery = '';
  fromArticle: ContentItemSummary | null = null;
  toArticle: ContentItemSummary | null = null;
  fromResults: ContentItemSummary[] = [];
  toResults: ContentItemSummary[] = [];
  pathResult: PathResult | null = null;
  loadingPath = false;
  private fromSearchSubject = new Subject<string>();
  private toSearchSubject = new Subject<string>();

  /** Tracks which tabs have been loaded at least once. */
  private loadedTabs = new Set<number>();

  constructor(private graphService: GraphService, private snack: MatSnackBar) {}

  ngOnInit(): void {
    this._setupEntitySearch();
    this._setupPathSearch();
    this._loadTab(0);
  }

  onTabChange(index: number): void {
    this.selectedTabIndex = index;
    this._loadTab(index);
  }

  private _loadTab(index: number): void {
    if (this.loadedTabs.has(index)) return;
    this.loadedTabs.add(index);

    switch (index) {
      case 0: this._loadStats(); break;
      case 1: this._loadTopics(); break;
      case 2: this._loadEntities(); break;
      case 3: this._loadHubs(); break;
      case 4: this._loadAudit(); break;
      case 5: this._loadTopology(); break;
      case 6: this._loadQuality(); break;
      // tab 7 (path) loads on demand via button
      case 8: this._loadFreshness(); break;
    }
  }

  // ── Stats ────────────────────────────────────────────────────────

  private _loadStats(): void {
    this.loadingStats = true;
    this.graphService.getStats().subscribe({
      next: (s) => { this.stats = s; this.loadingStats = false; },
      error: () => { this.loadingStats = false; },
    });
  }

  // ── Topics ───────────────────────────────────────────────────────

  private _loadTopics(): void {
    this.loadingTopics = true;
    this.graphService.getTopics().subscribe({
      next: (t) => { this.topics = t; this.loadingTopics = false; },
      error: () => { this.loadingTopics = false; },
    });
  }

  // ── Entities ─────────────────────────────────────────────────────

  private _setupEntitySearch(): void {
    this.entitySearchSubject
      .pipe(debounceTime(300), distinctUntilChanged())
      .subscribe(() => {
        this.entityPage = 1;
        this._fetchEntities();
      });
  }

  private _loadEntities(): void {
    this._fetchEntities();
  }

  private _fetchEntities(): void {
    this.loadingEntities = true;
    this.graphService
      .getEntities({ entity_type: this.entityTypeFilter, search: this.entitySearch, page: this.entityPage })
      .subscribe({
        next: (res) => {
          this.entities = res.results;
          this.entityCount = res.count;
          this.loadingEntities = false;
        },
        error: () => { this.loadingEntities = false; },
      });
  }

  onEntityTypeFilter(type: EntityType | ''): void {
    this.entityTypeFilter = type;
    this.entityPage = 1;
    this._fetchEntities();
  }

  onEntitySearchChange(value: string): void {
    this.entitySearchSubject.next(value);
  }

  onEntityPageChange(event: PageEvent): void {
    this.entityPage = event.pageIndex + 1;
    this._fetchEntities();
  }

  entityTypeLabel(type: EntityType): string {
    const map: Record<EntityType, string> = {
      keyword: 'Keyword',
      named_entity: 'Named Entity',
      topic_tag: 'Topic Tag',
    };
    return map[type] ?? type;
  }

  // ── Hub Articles ─────────────────────────────────────────────────

  private _loadHubs(): void {
    this.loadingHubs = true;
    this.graphService.getHubArticles(50).subscribe({
      next: (a) => { this.hubArticles = a; this.loadingHubs = false; },
      error: () => { this.loadingHubs = false; },
    });
  }

  pagerankBar(score: number): number {
    return Math.min(Math.round(score * 100), 100);
  }

  // ── Audits (Orphan & Low-Authority Pages) ────────────────────────

  private _loadAudit(): void {
    this.loadingAudit = true;
    this.graphService.getOrphans(this.auditPage, this.auditPageSize, this.auditMode).subscribe({
      next: (res) => {
        this.auditItems = res.results;
        this.auditCount = res.count;
        this.loadingAudit = false;
      },
      error: () => { this.loadingAudit = false; },
    });
  }

  onAuditPageChange(event: PageEvent): void {
    this.auditPage = event.pageIndex + 1;
    this.auditPageSize = event.pageSize;
    this._loadAudit();
  }

  onAuditModeChange(mode: AuditMode): void {
    this.auditMode = mode;
    this.auditPage = 1;
    this.loadedTabs.delete(4);
    this._loadAudit();
  }

  exportAuditCsv(): void {
    this.graphService.exportOrphansCsv(this.auditMode).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        const label = this.auditMode === 'low_authority' ? 'low-authority' : 'orphan';
        anchor.download = `${label}-audit-${new Date().toISOString().slice(0, 10)}.csv`;
        anchor.click();
        window.URL.revokeObjectURL(url);
      },
      error: () => {
        this.snack.open('Failed to export CSV', 'Dismiss', { duration: 4000 });
      },
    });
  }

  suggestLinks(item: ContentItemSummary): void {
    this.suggestingId = item.id;
    this.graphService.suggestLinksForOrphan(item.id).subscribe({
      next: () => {
        this.suggestingId = null;
        this.snack.open(`Pipeline started for "${item.title}"`, 'OK', { duration: 4000 });
      },
      error: () => {
        this.suggestingId = null;
        this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
      },
    });
  }

  focusInGraph(item: ContentItemSummary): void {
    this.selectedTabIndex = 5;
    this._loadTab(5);
    setTimeout(() => {
      const found = this.vizComponent?.focusNode(item.id);
      if (found === false) {
        this.snack.open(
          'This page is not in the network view (only the top 500 pages by authority are shown).',
          'OK',
          { duration: 5000 },
        );
      }
    }, 400);
  }

  // ── Path Explorer ─────────────────────────────────────────────────

  private _setupPathSearch(): void {
    this.fromSearchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q) => this.graphService.searchArticles(q))
      )
      .subscribe((res) => (this.fromResults = res));

    this.toSearchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q) => this.graphService.searchArticles(q))
      )
      .subscribe((res) => (this.toResults = res));
  }

  onFromInput(event: Event): void {
    this.fromArticle = null;
    this.fromSearchSubject.next((event.target as HTMLInputElement).value);
  }

  onToInput(event: Event): void {
    this.toArticle = null;
    this.toSearchSubject.next((event.target as HTMLInputElement).value);
  }

  onFromSelected(event: MatAutocompleteSelectedEvent): void {
    this.fromArticle = event.option.value as ContentItemSummary;
    this.fromQuery = this.fromArticle.title;
  }

  onToSelected(event: MatAutocompleteSelectedEvent): void {
    this.toArticle = event.option.value as ContentItemSummary;
    this.toQuery = this.toArticle.title;
  }

  displayArticle(article: ContentItemSummary | null): string {
    return article?.title ?? '';
  }

  findPath(): void {
    if (!this.fromArticle || !this.toArticle) return;
    this.loadingPath = true;
    this.pathResult = null;
    this.graphService.findPath(this.fromArticle.id, this.toArticle.id).subscribe({
      next: (res) => { this.pathResult = res; this.loadingPath = false; },
      error: () => { this.loadingPath = false; },
    });
  }

  canFindPath(): boolean {
    return !!this.fromArticle && !!this.toArticle && !this.loadingPath;
  }

  trackByPathNode(_i: number, node: PathNode): number {
    return node.id;
  }

  // ── Network Visualization ─────────────────────────────────────────

  private _loadTopology(onLoaded?: () => void, at?: string): void {
    if (!at && this.topology.nodes.length > 0 && !this.loadingTopology) {
      onLoaded?.();
      return;
    }
    this.loadingTopology = true;
    this.graphService.getTopology(500, at).subscribe({
      next: (t) => {
        this.topology = t;
        this.churnyIds = new Set(t.churny_ids);
        this.loadingTopology = false;
        if (!at) this._loadPageRankEquity();
        onLoaded?.();
      },
      error: () => { this.loadingTopology = false; },
    });
  }

  private _loadPageRankEquity(): void {
    this.loadingEquity = true;
    this.graphService.getPageRankEquity().subscribe({
      next: (eq) => { this.pageRankEquity = eq; this.loadingEquity = false; },
      error: () => { this.loadingEquity = false; },
    });
  }

  onHeatmapToggle(checked: boolean): void {
    this.heatmapMode = checked;
  }

  onHistoryModeChange(): void {
    if (!this.historyMode) {
      // Restore live topology when history mode is turned off.
      this.loadedTabs.delete(5);
      this._loadTopology();
    }
  }

  onHistoryDateChange(date: string): void {
    if (!date) return;
    this._loadTopology(undefined, date);
  }

  onNodeSelected(node: GraphNode | null): void {
    this.selectedNode = node;
    if (!node) {
      this.selectedNodeLinks = { inbound: [], outbound: [] };
      return;
    }
    this.selectedNodeLinks = {
      inbound: this.topology.links.filter((l) => l.target === node.id),
      outbound: this.topology.links.filter((l) => l.source === node.id),
    };
  }

  nodeTitle(id: number): string {
    return this.topology.nodes.find((n) => n.id === id)?.title ?? String(id);
  }

  // ── Qualities ─────────────────────────────────────────────────────

  private _loadQuality(): void {
    this._loadTopology(() => this._computeQuality());
  }

  private _computeQuality(): void {
    const { nodes, links } = this.topology;
    const total = links.length;
    if (total === 0) return;

    // Pie chart: links by context class
    const nContextual  = links.filter((l) => l.context === 'contextual').length;
    const nWeak        = links.filter((l) => l.context === 'weak_context').length;
    const nIsolated    = links.filter((l) => l.context === 'isolated').length;
    this.contextPieData = {
      labels: ['Contextual', 'Weak Context', 'Isolated'],
      datasets: [{
        data: [nContextual, nWeak, nIsolated],
        backgroundColor: ['#1a73e8', '#f9ab00', '#d93025'],
        borderWidth: 1,
        borderColor: '#fff',
      }],
    };

    // Anchor frequency bar chart (top 15)
    const anchorCount = new Map<string, number>();
    for (const l of links) {
      if (l.anchor) {
        anchorCount.set(l.anchor, (anchorCount.get(l.anchor) ?? 0) + 1);
      }
    }
    const sortedAnchors = [...anchorCount.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15);
    this.anchorBarData = {
      labels: sortedAnchors.map(([text]) => text.length > 30 ? text.slice(0, 30) + '\u2026' : text),
      datasets: [{
        label: 'Link count',
        data: sortedAnchors.map(([, count]) => count),
        backgroundColor: '#1a73e8',
      }],
    };

    // Anchor warnings: any single anchor > 5% of all links
    this.anchorWarnings = sortedAnchors
      .filter(([, count]) => count / total > 0.05)
      .map(([anchor, count]) => ({ anchor, count, pct: Math.round(count / total * 100) }));

    // Per-page quality scores (grouped by target page)
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const inboundMap = new Map<number, { contextual: number; total: number }>();
    for (const l of links) {
      const entry = inboundMap.get(l.target) ?? { contextual: 0, total: 0 };
      entry.total++;
      if (l.context === 'contextual') entry.contextual++;
      inboundMap.set(l.target, entry);
    }
    this.pageQualityRows = [...inboundMap.entries()]
      .map(([id, { contextual: ctx, total: tot }]) => {
        const pct = Math.round(ctx / tot * 100);
        return {
          id,
          title: nodeMap.get(id)?.title ?? String(id),
          inbound: tot,
          contextual: ctx,
          contextualPct: pct,
          qualityLabel: (pct >= 75 ? 'High' : pct >= 40 ? 'Medium' : 'Low') as 'High' | 'Medium' | 'Low',
        };
      })
      .sort((a, b) => a.contextualPct - b.contextualPct);

    // Isolated links list (capped at 200 rows for performance)
    this.isolatedLinks = links
      .filter((l) => l.context === 'isolated')
      .slice(0, 200)
      .map((l) => ({
        source: l.source,
        srcTitle: nodeMap.get(l.source)?.title ?? String(l.source),
        target: l.target,
        tgtTitle: nodeMap.get(l.target)?.title ?? String(l.target),
        anchor: l.anchor,
      }));
  }

  onIsolatedRowHover(row: IsolatedLinkRow | null): void {
    this.highlightEdge = row ? { source: row.source, target: row.target } : null;
  }

  jumpToNetworkTab(source: number, target: number): void {
    this.highlightEdge = { source, target };
    this.selectedTabIndex = 5;
    this._loadTab(5);
  }

  qualityBadgeClass(label: 'High' | 'Medium' | 'Low'): string {
    return label === 'High' ? 'quality-high' : label === 'Medium' ? 'quality-medium' : 'quality-low';
  }

  // ── Freshness ─────────────────────────────────────────────────────

  private _loadFreshness(): void {
    // Reuse topology already fetched for the Network tab; fetch if not yet loaded.
    if (this.topology.nodes.length === 0) {
      this.loadingFreshness = true;
      this._loadTopology(() => { this._buildVelocityChart(); this.loadingFreshness = false; });
    } else {
      this._buildVelocityChart();
    }
  }

  private _buildVelocityChart(): void {
    const history: HistoryPoint[] = this.topology.history;
    if (history.length === 0) {
      this.velocityChartData = { labels: [], datasets: [] };
      this.churnTable = [];
      return;
    }

    this.velocityChartData = {
      labels: history.map((h) => h.date),
      datasets: [
        {
          label: 'Links Created',
          data: history.map((h) => h.created),
          fill: true,
          borderColor: '#1a73e8',
          backgroundColor: 'rgba(26,115,232,0.12)',
          pointRadius: 3,
          tension: 0.3,
        },
        {
          label: 'Links Disappeared',
          data: history.map((h) => h.deleted),
          fill: true,
          borderColor: '#c5221f',
          backgroundColor: 'rgba(197,34,31,0.12)',
          pointRadius: 3,
          tension: 0.3,
        },
      ],
    };

    this.churnTable = this.topology.churny_nodes;
  }
}
