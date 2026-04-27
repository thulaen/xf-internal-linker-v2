import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, TemplateRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatSliderModule } from '@angular/material/slider';
import { catchError, debounceTime, distinctUntilChanged, of, Subject, switchMap, timer } from 'rxjs';
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
  GapAnalysis,
  GhostEdge,
} from './graph.service';
import { LinkGraphVizComponent } from './link-graph-viz/link-graph-viz.component';
import { PersistTabDirective } from '../core/directives/persist-tab.directive';

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

const EMPTY_TOPOLOGY: GraphTopology = { nodes: [], links: [], history: [], churny_ids: [], churny_nodes: [] };
const EMPTY_NODE_LINKS = { inbound: [] as GraphLink[], outbound: [] as GraphLink[] };

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
    MatDialogModule,
    MatSliderModule,
    LinkGraphVizComponent,
    BaseChartDirective,
    // Phase NV / Gap 145 — restores last-viewed tab on return visits.
    PersistTabDirective,
  ],
  templateUrl: './graph.component.html',
  styleUrls: ['./graph.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GraphComponent implements OnInit {
  @ViewChild(LinkGraphVizComponent) private vizComponent?: LinkGraphVizComponent;
  @ViewChild('quickApproveDialog') private quickApproveDialogRef!: TemplateRef<unknown>;

  readonly selectedTabIndex = signal(0);

  // ── Tab 1: Overview ──────────────────────────────────────────────
  readonly stats = signal<GraphStats | null>(null);
  readonly loadingStats = signal(false);

  // ── Tab 2: Topics ────────────────────────────────────────────────
  readonly topics = signal<SiloGroupSummary[]>([]);
  readonly loadingTopics = signal(false);

  // ── Tab 3: Entities ──────────────────────────────────────────────
  readonly entities = signal<EntityNode[]>([]);
  readonly entityCount = signal(0);
  readonly loadingEntities = signal(false);
  readonly entityTypeFilter = signal<EntityType | ''>('');
  /** ngModel two-way binding — needs an lvalue, stays plain. The
   *  (ngModelChange) handler pushes into `entitySearchSubject` for
   *  debounce; OnPush sees CD per keystroke through the event handler. */
  entitySearch = '';
  readonly entityPage = signal(1);
  readonly entityColumns: readonly string[] = ['canonical_form', 'entity_type', 'article_count'];
  private entitySearchSubject = new Subject<string>();

  // ── Tab 4: Hub Articles ──────────────────────────────────────────
  readonly hubArticles = signal<ContentItemSummary[]>([]);
  readonly loadingHubs = signal(false);
  readonly hubColumns: readonly string[] = ['title', 'content_type_label', 'march_2026_pagerank_score'];

  // ── Tab 5: Audits (Orphan & Low-Authority Pages) ─────────────────
  readonly auditItems = signal<ContentItemSummary[]>([]);
  readonly auditCount = signal(0);
  readonly loadingAudit = signal(false);
  readonly auditPage = signal(1);
  readonly auditPageSize = signal(50);
  readonly auditMode = signal<AuditMode>('orphan');
  readonly auditColumns: readonly string[] = ['title', 'scope_title', 'inbound_link_count', 'march_2026_pagerank_score', 'actions'];
  readonly suggestingId = signal<number | null>(null);

  // ── Tab 6: Network Visualization ────────────────────────────────
  readonly topology = signal<GraphTopology>(EMPTY_TOPOLOGY);
  readonly loadingTopology = signal(false);
  readonly selectedNode = signal<GraphNode | null>(null);
  readonly selectedNodeLinks = signal<{ inbound: GraphLink[]; outbound: GraphLink[] }>(EMPTY_NODE_LINKS);
  readonly heatmapMode = signal(false);
  readonly historyMode = signal(false);
  /** ngModel two-way on a `<input type="date">` — stays plain. */
  historyDate = '';
  readonly churnyIds = signal<Set<number>>(new Set());
  readonly pageRankEquity = signal<PageRankEquity | null>(null);
  readonly loadingEquity = signal(false);
  readonly authorityColumns: readonly string[] = ['rank', 'title', 'silo_name', 'in_degree', 'out_degree', 'pagerank'];
  readonly today = new Date().toISOString().slice(0, 10);

  // ── Tab 9: Freshness ─────────────────────────────────────────────
  readonly velocityChartData = signal<ChartData<'line'> | null>(null);
  readonly velocityChartOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { position: 'top' } },
    scales: {
      x: { ticks: { maxTicksLimit: 15, font: { size: 11 } } },
      y: { stacked: false, beginAtZero: true, ticks: { precision: 0 } },
    },
  };
  readonly churnTable = signal<ChurnNode[]>([]);
  readonly loadingFreshness = signal(false);
  readonly churnColumns: readonly string[] = ['title', 'churn_count'];

  // ── Tab 6: Network Visualization — Coverage Gaps overlay ─────────
  readonly showGapsOverlay = signal(false);
  readonly activeGhostEdge = signal<GhostEdge | null>(null);
  private _gapDialogRef: MatDialogRef<unknown> | null = null;

  // ── Tab 10: Coverage Gaps ─────────────────────────────────────────
  readonly gapData = signal<GapAnalysis | null>(null);
  /** ngModel two-way on the threshold slider — stays plain. */
  gapThreshold = 0.8;
  readonly loadingGaps = signal(false);
  readonly gapNodeColumns: readonly string[] = ['title', 'inbound_count', 'pending_suggestion_count', 'neglect_score'];

  // ── Tab 6: Qualities ─────────────────────────────────────────────
  readonly contextFilter = signal<'all' | 'contextual'>('all');
  readonly highlightEdge = signal<{ source: number; target: number } | null>(null);
  readonly contextPieData = signal<ChartData<'pie'> | null>(null);
  readonly anchorBarData = signal<ChartData<'bar'> | null>(null);
  readonly pageQualityRows = signal<PageQualityRow[]>([]);
  readonly isolatedLinks = signal<IsolatedLinkRow[]>([]);
  readonly anchorWarnings = signal<AnchorWarning[]>([]);
  readonly qualityColumns: readonly string[] = ['title', 'inbound', 'contextualPct', 'qualityLabel'];
  readonly isolatedColumns: readonly string[] = ['srcTitle', 'tgtTitle', 'anchor', 'jump'];

  // ── Tab 7: Path Explorer ─────────────────────────────────────────
  /** ngModel two-way on autocomplete inputs — stay plain. */
  fromQuery = '';
  toQuery = '';
  readonly fromArticle = signal<ContentItemSummary | null>(null);
  readonly toArticle = signal<ContentItemSummary | null>(null);
  readonly fromResults = signal<ContentItemSummary[]>([]);
  readonly toResults = signal<ContentItemSummary[]>([]);
  readonly pathResult = signal<PathResult | null>(null);
  readonly loadingPath = signal(false);
  private fromSearchSubject = new Subject<string>();
  private toSearchSubject = new Subject<string>();

  /** Tracks which tabs have been loaded at least once. */
  private loadedTabs = new Set<number>();

  private destroyRef = inject(DestroyRef);

  constructor(
    private graphService: GraphService,
    private snack: MatSnackBar,
    private dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this._setupEntitySearch();
    this._setupPathSearch();
    this._loadTab(0);
  }

  onTabChange(index: number): void {
    this.selectedTabIndex.set(index);
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
      case 9: this._loadGaps(); break;
    }
  }

  // ── Stats ────────────────────────────────────────────────────────

  private _loadStats(): void {
    this.loadingStats.set(true);
    this.graphService.getStats()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => { this.stats.set(s); this.loadingStats.set(false); },
        error: () => this.loadingStats.set(false),
      });
  }

  // ── Topics ───────────────────────────────────────────────────────

  private _loadTopics(): void {
    this.loadingTopics.set(true);
    this.graphService.getTopics()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (t) => { this.topics.set(t); this.loadingTopics.set(false); },
        error: () => this.loadingTopics.set(false),
      });
  }

  // ── Entities ─────────────────────────────────────────────────────

  private _setupEntitySearch(): void {
    this.entitySearchSubject
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.entityPage.set(1);
        this._fetchEntities();
      });
  }

  private _loadEntities(): void {
    this._fetchEntities();
  }

  private _fetchEntities(): void {
    this.loadingEntities.set(true);
    this.graphService
      .getEntities({
        entity_type: this.entityTypeFilter(),
        search: this.entitySearch,
        page: this.entityPage(),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.entities.set(res.results);
          this.entityCount.set(res.count);
          this.loadingEntities.set(false);
        },
        error: () => this.loadingEntities.set(false),
      });
  }

  onEntityTypeFilter(type: EntityType | ''): void {
    this.entityTypeFilter.set(type);
    this.entityPage.set(1);
    this._fetchEntities();
  }

  onEntitySearchChange(value: string): void {
    this.entitySearchSubject.next(value);
  }

  onEntityPageChange(event: PageEvent): void {
    this.entityPage.set(event.pageIndex + 1);
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
    this.loadingHubs.set(true);
    this.graphService.getHubArticles(50)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (a) => { this.hubArticles.set(a); this.loadingHubs.set(false); },
        error: () => this.loadingHubs.set(false),
      });
  }

  pagerankBar(score: number): number {
    return Math.min(Math.round(score * 100), 100);
  }

  // ── Audits (Orphan & Low-Authority Pages) ────────────────────────

  private _loadAudit(): void {
    this.loadingAudit.set(true);
    this.graphService.getOrphans(this.auditPage(), this.auditPageSize(), this.auditMode())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.auditItems.set(res.results);
          this.auditCount.set(res.count);
          this.loadingAudit.set(false);
        },
        error: () => this.loadingAudit.set(false),
      });
  }

  onAuditPageChange(event: PageEvent): void {
    this.auditPage.set(event.pageIndex + 1);
    this.auditPageSize.set(event.pageSize);
    this._loadAudit();
  }

  onAuditModeChange(mode: AuditMode): void {
    this.auditMode.set(mode);
    this.auditPage.set(1);
    this.loadedTabs.delete(4);
    this._loadAudit();
  }

  exportAuditCsv(): void {
    this.graphService.exportOrphansCsv(this.auditMode())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          const url = window.URL.createObjectURL(blob);
          const anchor = document.createElement('a');
          anchor.href = url;
          const label = this.auditMode() === 'low_authority' ? 'low-authority' : 'orphan';
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
    this.suggestingId.set(item.id);
    this.graphService.suggestLinksForOrphan(item.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.suggestingId.set(null);
          this.snack.open(`Pipeline started for "${item.title}"`, 'OK', { duration: 4000 });
        },
        error: () => {
          this.suggestingId.set(null);
          this.snack.open('Failed to start pipeline', 'Dismiss', { duration: 4000 });
        },
      });
  }

  focusInGraph(item: ContentItemSummary): void {
    this.selectedTabIndex.set(5);
    this._loadTab(5);
    // Wait for the network tab to render and the D3 viz to mount its
    // SVG before asking it to focus a node. `timer + takeUntilDestroyed`
    // cancels on route navigation — the previous bare setTimeout would
    // fire `vizComponent?.focusNode()` against a dead component if the
    // user navigated away during the 400ms tab transition.
    timer(400).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      const found = this.vizComponent?.focusNode(item.id);
      if (found === false) {
        this.snack.open(
          'This page is not in the network view (only the top 500 pages by authority are shown).',
          'OK',
          { duration: 5000 },
        );
      }
    });
  }

  // ── Path Explorer ─────────────────────────────────────────────────

  private _setupPathSearch(): void {
    this.fromSearchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q) =>
          this.graphService.searchArticles(q).pipe(catchError(() => of([] as ContentItemSummary[])))
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => this.fromResults.set(res));

    this.toSearchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((q) =>
          this.graphService.searchArticles(q).pipe(catchError(() => of([] as ContentItemSummary[])))
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => this.toResults.set(res));
  }

  onFromInput(event: Event): void {
    this.fromArticle.set(null);
    this.fromSearchSubject.next((event.target as HTMLInputElement).value);
  }

  onToInput(event: Event): void {
    this.toArticle.set(null);
    this.toSearchSubject.next((event.target as HTMLInputElement).value);
  }

  onFromSelected(event: MatAutocompleteSelectedEvent): void {
    const article = event.option.value as ContentItemSummary;
    this.fromArticle.set(article);
    this.fromQuery = article.title;
  }

  onToSelected(event: MatAutocompleteSelectedEvent): void {
    const article = event.option.value as ContentItemSummary;
    this.toArticle.set(article);
    this.toQuery = article.title;
  }

  displayArticle(article: ContentItemSummary | null): string {
    return article?.title ?? '';
  }

  findPath(): void {
    const from = this.fromArticle();
    const to = this.toArticle();
    if (!from || !to) return;
    this.loadingPath.set(true);
    this.pathResult.set(null);
    this.graphService.findPath(from.id, to.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => { this.pathResult.set(res); this.loadingPath.set(false); },
        error: () => this.loadingPath.set(false),
      });
  }

  canFindPath(): boolean {
    return !!this.fromArticle() && !!this.toArticle() && !this.loadingPath();
  }

  trackByPathNode(_i: number, node: PathNode): number {
    return node.id;
  }

  trackByTopicId(_i: number, topic: SiloGroupSummary): number {
    return topic.id;
  }

  trackByArticleId(_i: number, a: ContentItemSummary): number {
    return a.id;
  }

  // ── Network Visualization ─────────────────────────────────────────

  private _loadTopology(onLoaded?: () => void, at?: string): void {
    if (!at && this.topology().nodes.length > 0 && !this.loadingTopology()) {
      onLoaded?.();
      return;
    }
    this.loadingTopology.set(true);
    this.graphService.getTopology(500, at)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (t) => {
          this.topology.set(t);
          this.churnyIds.set(new Set(t.churny_ids));
          this.loadingTopology.set(false);
          if (!at) this._loadPageRankEquity();
          onLoaded?.();
        },
        error: () => this.loadingTopology.set(false),
      });
  }

  private _loadPageRankEquity(): void {
    this.loadingEquity.set(true);
    this.graphService.getPageRankEquity()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (eq) => { this.pageRankEquity.set(eq); this.loadingEquity.set(false); },
        error: () => this.loadingEquity.set(false),
      });
  }

  onHeatmapToggle(checked: boolean): void {
    this.heatmapMode.set(checked);
  }

  onHistoryModeChange(): void {
    if (!this.historyMode()) {
      // Restore live topology when history mode is turned off.
      this.loadedTabs.delete(5);
      this._loadTopology();
    }
  }

  onHistoryDateChange(date: string): void {
    if (!date) return;
    this._loadTopology(undefined, date);
  }

  /** Two-way bound on a mat-slide-toggle. Setter exposed because the
   *  template binds `(change)="onHistoryModeChange()"` after toggling
   *  via [(ngModel)]. */
  setHistoryMode(value: boolean): void {
    this.historyMode.set(value);
  }

  setContextFilter(value: 'all' | 'contextual'): void {
    this.contextFilter.set(value);
  }

  onNodeSelected(node: GraphNode | null): void {
    this.selectedNode.set(node);
    if (!node) {
      this.selectedNodeLinks.set(EMPTY_NODE_LINKS);
      return;
    }
    const links = this.topology().links;
    this.selectedNodeLinks.set({
      inbound: links.filter((l) => l.target === node.id),
      outbound: links.filter((l) => l.source === node.id),
    });
  }

  nodeTitle(id: number): string {
    return this.topology().nodes.find((n) => n.id === id)?.title ?? String(id);
  }

  // ── Qualities ─────────────────────────────────────────────────────

  private _loadQuality(): void {
    this._loadTopology(() => this._computeQuality());
  }

  private _computeQuality(): void {
    const { nodes, links } = this.topology();
    const total = links.length;
    if (total === 0) return;

    // Pie chart: links by context class
    const nContextual  = links.filter((l) => l.context === 'contextual').length;
    const nWeak        = links.filter((l) => l.context === 'weak_context').length;
    const nIsolated    = links.filter((l) => l.context === 'isolated').length;
    this.contextPieData.set({
      labels: ['Contextual', 'Weak Context', 'Isolated'],
      datasets: [{
        data: [nContextual, nWeak, nIsolated],
        backgroundColor: ['#1a73e8', '#f9ab00', '#d93025'],
        borderWidth: 1,
        borderColor: '#fff',
      }],
    });

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

    this.anchorBarData.set({
      labels: sortedAnchors.map(([text]) => text.length > 30 ? text.slice(0, 30) + '…' : text),
      datasets: [{
        label: 'Link count',
        data: sortedAnchors.map(([, count]) => count),
        backgroundColor: '#1a73e8',
      }],
    });

    // Anchor warnings: any single anchor > 5% of all links
    this.anchorWarnings.set(
      sortedAnchors
        .filter(([, count]) => count / total > 0.05)
        .map(([anchor, count]) => ({ anchor, count, pct: Math.round(count / total * 100) })),
    );

    // Per-page quality scores (grouped by target page)
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const inboundMap = new Map<number, { contextual: number; total: number }>();
    for (const l of links) {
      const entry = inboundMap.get(l.target) ?? { contextual: 0, total: 0 };
      entry.total++;
      if (l.context === 'contextual') entry.contextual++;
      inboundMap.set(l.target, entry);
    }
    this.pageQualityRows.set(
      [...inboundMap.entries()]
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
        .sort((a, b) => a.contextualPct - b.contextualPct),
    );

    // Isolated links list (capped at 200 rows for performance)
    this.isolatedLinks.set(
      links
        .filter((l) => l.context === 'isolated')
        .slice(0, 200)
        .map((l) => ({
          source: l.source,
          srcTitle: nodeMap.get(l.source)?.title ?? String(l.source),
          target: l.target,
          tgtTitle: nodeMap.get(l.target)?.title ?? String(l.target),
          anchor: l.anchor,
        })),
    );
  }

  onIsolatedRowHover(row: IsolatedLinkRow | null): void {
    this.highlightEdge.set(row ? { source: row.source, target: row.target } : null);
  }

  jumpToNetworkTab(source: number, target: number): void {
    this.highlightEdge.set({ source, target });
    this.selectedTabIndex.set(5);
    this._loadTab(5);
  }

  qualityBadgeClass(label: 'High' | 'Medium' | 'Low'): string {
    return label === 'High' ? 'quality-high' : label === 'Medium' ? 'quality-medium' : 'quality-low';
  }

  // ── Freshness ─────────────────────────────────────────────────────

  private _loadFreshness(): void {
    // Reuse topology already fetched for the Network tab; fetch if not yet loaded.
    if (this.topology().nodes.length === 0) {
      this.loadingFreshness.set(true);
      this._loadTopology(() => { this._buildVelocityChart(); this.loadingFreshness.set(false); });
    } else {
      this._buildVelocityChart();
    }
  }

  // ── Coverage Gaps ─────────────────────────────────────────────────

  private _loadGaps(): void {
    this.loadingGaps.set(true);
    this.graphService.getGapAnalysis(this.gapThreshold)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => { this.gapData.set(data); this.loadingGaps.set(false); },
        error: () => this.loadingGaps.set(false),
      });
  }

  reloadGaps(): void {
    this.loadedTabs.delete(9);
    this._loadGaps();
  }

  onGapsOverlayToggle(): void {
    if (this.showGapsOverlay() && !this.gapData()) {
      this._loadGaps();
    }
  }

  setShowGapsOverlay(value: boolean): void {
    this.showGapsOverlay.set(value);
  }

  onGhostEdgeClicked(edge: GhostEdge): void {
    this.activeGhostEdge.set(edge);
    this._gapDialogRef = this.dialog.open(this.quickApproveDialogRef, { width: '480px' });
    this._gapDialogRef.afterClosed()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.activeGhostEdge.set(null));
  }

  approveGhostEdge(): void {
    const edge = this.activeGhostEdge();
    if (!edge) return;
    this.graphService.approveSuggestion(edge.suggestion_id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Atomic update — produce a new GapAnalysis with the approved
          // edge filtered out and the count decremented in one signal write.
          this.gapData.update((curr) => {
            if (!curr) return curr;
            return {
              ...curr,
              ghost_edges: curr.ghost_edges.filter((ge) => ge.suggestion_id !== edge.suggestion_id),
              total_ghost_edges: curr.total_ghost_edges - 1,
            };
          });
          this._gapDialogRef?.close();
          this.snack.open('Suggestion approved', 'OK', { duration: 3000 });
        },
        error: () => {
          this.snack.open('Failed to approve suggestion', 'Dismiss', { duration: 4000 });
        },
      });
  }

  private _buildVelocityChart(): void {
    const history: HistoryPoint[] = this.topology().history;
    if (history.length === 0) {
      this.velocityChartData.set({ labels: [], datasets: [] });
      this.churnTable.set([]);
      return;
    }

    this.velocityChartData.set({
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
    });

    this.churnTable.set(this.topology().churny_nodes);
  }
}
