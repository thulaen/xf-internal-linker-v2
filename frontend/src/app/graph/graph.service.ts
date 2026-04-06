import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

// ── Interfaces ────────────────────────────────────────────────────────────────

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  entity_count: number;
  orphan_count: number;
  connected_pct: number;
  topic_count: number;
}

export type EntityType = 'keyword' | 'named_entity' | 'topic_tag';

export interface EntityNode {
  id: number;
  entity_id: string;
  surface_form: string;
  canonical_form: string;
  entity_type: EntityType;
  article_count: number;
  created_at: string;
}

export interface PathNode {
  id: number;
  title: string;
  url: string;
}

export interface PathResult {
  found: boolean;
  path: PathNode[];
  hops: number;
}

export interface PaginatedResult<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ContentItemSummary {
  id: number;
  content_id: string;
  content_type: string;
  content_type_label: string;
  title: string;
  url: string;
  scope_title: string;
  march_2026_pagerank_score: number;
  velocity_score: number;
  inbound_link_count: number;
  post_date: string | null;
  is_deleted: boolean;
}

export interface GraphNode {
  id: number;
  title: string;
  type: string;
  silo_id: number;
  pagerank: number;
  in_degree: number;
  out_degree: number;
}

export interface GraphLink {
  source: number;
  target: number;
  context: string;
  anchor: string;
  weight: number;
}

export interface HistoryPoint {
  date: string;
  created: number;
  deleted: number;
}

export interface ChurnNode {
  id: number;
  title: string;
  churn_count: number;
}

export interface GraphTopology {
  nodes: GraphNode[];
  links: GraphLink[];
  history: HistoryPoint[];
  churny_ids: number[];
  churny_nodes: ChurnNode[];
}

export interface SiloGroupSummary {
  id: number;
  name: string;
  slug: string;
  description: string;
  scope_count: number;
}

export type AuditMode = 'orphan' | 'low_authority';

export interface PageRankAuthority {
  id: number;
  title: string;
  url: string;
  silo_name: string;
  pagerank: number;
  in_degree: number;
  out_degree: number;
}

export interface PageRankEquity {
  pr_min: number;
  pr_max: number;
  total_nodes: number;
  concentration_warning: boolean;
  concentration_ratio: number;
  top_authorities: PageRankAuthority[];
}

export interface EntityParams {
  entity_type?: EntityType | '';
  search?: string;
  page?: number;
}

export interface GapNode {
  id: number;
  title: string;
  url: string;
  neglect_score: number;
  inbound_count: number;
  pending_suggestion_count: number;
}

export interface GhostEdge {
  source: number;
  target: number;
  score_final: number;
  anchor_phrase: string;
  suggestion_id: string;
  score_semantic: number;
  score_keyword: number;
}

export interface GapAnalysis {
  nodes: GapNode[];
  ghost_edges: GhostEdge[];
  threshold: number;
  total_ghost_edges: number;
}

// ── Service ───────────────────────────────────────────────────────────────────

@Injectable({ providedIn: 'root' })
export class GraphService {
  private http = inject(HttpClient);
  private base = '/api';

  getStats(): Observable<GraphStats> {
    return this.http.get<GraphStats>(`${this.base}/graph/stats/`).pipe(
      catchError(() => of({
        total_nodes: 0, total_edges: 0, entity_count: 0,
        orphan_count: 0, connected_pct: 0, topic_count: 0,
      }))
    );
  }

  getTopics(): Observable<SiloGroupSummary[]> {
    return this.http
      .get<PaginatedResult<SiloGroupSummary> | SiloGroupSummary[]>(`${this.base}/silo-groups/`)
      .pipe(
        map((res) => (Array.isArray(res) ? res : res.results)),
        catchError(() => of([]))
      );
  }

  getEntities(params: EntityParams = {}): Observable<PaginatedResult<EntityNode>> {
    let httpParams = new HttpParams();
    if (params.entity_type) httpParams = httpParams.set('entity_type', params.entity_type);
    if (params.search) httpParams = httpParams.set('search', params.search);
    if (params.page) httpParams = httpParams.set('page', String(params.page));

    return this.http
      .get<PaginatedResult<EntityNode>>(`${this.base}/graph/entities/`, { params: httpParams })
      .pipe(catchError(() => of({ count: 0, next: null, previous: null, results: [] })));
  }

  getHubArticles(limit: number = 50): Observable<ContentItemSummary[]> {
    const params = new HttpParams()
      .set('ordering', '-march_2026_pagerank_score')
      .set('page_size', String(limit));
    return this.http
      .get<PaginatedResult<ContentItemSummary>>(`${this.base}/content/`, { params })
      .pipe(
        map((res) => res.results),
        catchError(() => of([]))
      );
  }

  getOrphans(page: number = 1, pageSize: number = 50, mode: AuditMode = 'orphan'): Observable<PaginatedResult<ContentItemSummary>> {
    const params = new HttpParams()
      .set('page', String(page))
      .set('page_size', String(pageSize))
      .set('mode', mode);
    return this.http
      .get<PaginatedResult<ContentItemSummary>>(`${this.base}/graph/orphans/`, { params })
      .pipe(catchError(() => of({ count: 0, next: null, previous: null, results: [] })));
  }

  exportOrphansCsv(mode: AuditMode = 'orphan'): Observable<Blob> {
    const params = new HttpParams().set('mode', mode);
    return this.http.get(`${this.base}/graph/orphans/export-csv/`, {
      params,
      responseType: 'blob',
    });
  }

  suggestLinksForOrphan(contentItemId: number): Observable<unknown> {
    return this.http.post(`${this.base}/graph/orphans/${contentItemId}/suggest/`, {});
  }

  findPath(fromId: number, toId: number): Observable<PathResult> {
    const params = new HttpParams()
      .set('from_id', String(fromId))
      .set('to_id', String(toId));
    return this.http
      .get<PathResult>(`${this.base}/graph/path/`, { params })
      .pipe(catchError(() => of({ found: false, path: [], hops: 0 })));
  }

  getTopology(limit = 500, at?: string): Observable<GraphTopology> {
    let params = new HttpParams().set('limit', String(limit));
    if (at) params = params.set('at', at);
    return this.http
      .get<GraphTopology>(`${this.base}/graph/topology/`, { params })
      .pipe(catchError(() => of({ nodes: [], links: [], history: [], churny_ids: [], churny_nodes: [] })));
  }

  getPageRankEquity(): Observable<PageRankEquity | null> {
    return this.http
      .get<PageRankEquity>(`${this.base}/graph/pagerank-equity/`)
      .pipe(catchError(() => of(null)));
  }

  approveSuggestion(suggestionId: string): Observable<unknown> {
    return this.http.post(`${this.base}/suggestions/${suggestionId}/approve/`, {});
  }

  getGapAnalysis(threshold = 0.8, limit = 300): Observable<GapAnalysis> {
    const params = new HttpParams()
      .set('threshold', threshold.toString())
      .set('limit', limit.toString());
    return this.http
      .get<GapAnalysis>(`${this.base}/graph/gap-analysis/`, { params })
      .pipe(catchError(() => of({ nodes: [], ghost_edges: [], threshold, total_ghost_edges: 0 })));
  }

  searchArticles(query: string): Observable<ContentItemSummary[]> {
    if (!query.trim()) return of([]);
    const params = new HttpParams().set('search', query).set('page_size', '20');
    return this.http
      .get<PaginatedResult<ContentItemSummary>>(`${this.base}/content/`, { params })
      .pipe(
        map((res) => res.results),
        catchError(() => of([]))
      );
  }
}
