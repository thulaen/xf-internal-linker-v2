import { Component, OnInit } from '@angular/core';
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
import { debounceTime, distinctUntilChanged, Subject, switchMap } from 'rxjs';

import {
  GraphService,
  GraphStats,
  EntityNode,
  EntityType,
  ContentItemSummary,
  SiloGroupSummary,
  PathResult,
  PathNode,
} from './graph.service';

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
  ],
  templateUrl: './graph.component.html',
  styleUrls: ['./graph.component.scss'],
})
export class GraphComponent implements OnInit {
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

  // ── Tab 5: Orphan Articles ───────────────────────────────────────
  orphans: ContentItemSummary[] = [];
  orphanCount = 0;
  loadingOrphans = false;
  orphanPage = 1;
  orphanPageSize = 50;
  orphanColumns = ['title', 'content_type_label', 'post_date'];

  // ── Tab 6: Path Explorer ─────────────────────────────────────────
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

  constructor(private graphService: GraphService) {}

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
      case 4: this._loadOrphans(); break;
      // tab 5 (path) loads on demand via button
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

  // ── Orphan Articles ──────────────────────────────────────────────

  private _loadOrphans(): void {
    this.loadingOrphans = true;
    this.graphService.getOrphans(this.orphanPage, this.orphanPageSize).subscribe({
      next: (res) => {
        this.orphans = res.results;
        this.orphanCount = res.count;
        this.loadingOrphans = false;
      },
      error: () => { this.loadingOrphans = false; },
    });
  }

  onOrphanPageChange(event: PageEvent): void {
    this.orphanPage = event.pageIndex + 1;
    this.orphanPageSize = event.pageSize;
    this.loadingOrphans = true;
    this.graphService.getOrphans(this.orphanPage, this.orphanPageSize).subscribe({
      next: (res) => {
        this.orphans = res.results;
        this.orphanCount = res.count;
        this.loadingOrphans = false;
      },
      error: () => { this.loadingOrphans = false; },
    });
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
}
