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
  march_2026_pagerank_score: number;
  velocity_score: number;
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
  weight: number;
}

export interface GraphTopology {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface SiloGroupSummary {
  id: number;
  name: string;
  slug: string;
  description: string;
  scope_count: number;
}

export interface EntityParams {
  entity_type?: EntityType | '';
  search?: string;
  page?: number;
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

  getOrphans(page: number = 1, pageSize: number = 50): Observable<PaginatedResult<ContentItemSummary>> {
    const params = new HttpParams()
      .set('page', String(page))
      .set('page_size', String(pageSize));
    return this.http
      .get<PaginatedResult<ContentItemSummary>>(`${this.base}/graph/orphans/`, { params })
      .pipe(catchError(() => of({ count: 0, next: null, previous: null, results: [] })));
  }

  findPath(fromId: number, toId: number): Observable<PathResult> {
    const params = new HttpParams()
      .set('from_id', String(fromId))
      .set('to_id', String(toId));
    return this.http
      .get<PathResult>(`${this.base}/graph/path/`, { params })
      .pipe(catchError(() => of({ found: false, path: [], hops: 0 })));
  }

  getTopology(limit = 500): Observable<GraphTopology> {
    const params = new HttpParams().set('limit', String(limit));
    return this.http
      .get<GraphTopology>(`${this.base}/graph/topology/`, { params })
      .pipe(catchError(() => of({ nodes: [], links: [] })));
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
