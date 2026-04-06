import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';

import { GraphComponent } from './graph.component';
import { GraphService } from './graph.service';

const graphServiceStub = {
  getStats:        () => of({ total_nodes: 0, total_edges: 0, entity_count: 0, orphan_count: 0, connected_pct: 0, topic_count: 0 }),
  getTopics:       () => of([]),
  getEntities:     () => of({ count: 0, next: null, previous: null, results: [] }),
  getHubArticles:  () => of([]),
  getOrphans:      () => of({ count: 0, next: null, previous: null, results: [] }),
  exportOrphansCsv:() => of(new Blob()),
  getTopology:     () => of({ nodes: [], links: [] }),
  getPageRankEquity: () => of(null),
  searchArticles:  () => of([]),
  findPath:        () => of({ found: false, path: [], hops: 0 }),
  suggestLinksForOrphan: () => of({}),
};

describe('GraphComponent — _computeQuality()', () => {
  let component: GraphComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [GraphComponent, NoopAnimationsModule],
      providers: [
        { provide: GraphService, useValue: graphServiceStub },
        { provide: ActivatedRoute, useValue: {} },
        provideCharts(withDefaultRegisterables()),
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(GraphComponent);
    component = fixture.componentInstance;
  });

  it('should build pie chart data from topology links', () => {
    component.topology = {
      nodes: [
        { id: 1, title: 'Page A', type: 'thread', silo_id: 0, pagerank: 0.1, in_degree: 1, out_degree: 0 },
        { id: 2, title: 'Page B', type: 'thread', silo_id: 0, pagerank: 0.2, in_degree: 0, out_degree: 1 },
      ],
      links: [
        { source: 2, target: 1, context: 'contextual',  anchor: 'click here', weight: 1 },
        { source: 2, target: 1, context: 'weak_context', anchor: 'read more', weight: 1 },
        { source: 2, target: 1, context: 'isolated',    anchor: '',           weight: 1 },
      ],
    };

    (component as any)._computeQuality();

    expect(component.contextPieData).toBeTruthy();
    const counts = component.contextPieData!.datasets[0].data as number[];
    expect(counts[0]).toBe(1); // contextual
    expect(counts[1]).toBe(1); // weak_context
    expect(counts[2]).toBe(1); // isolated
  });

  it('should flag over-used anchors as warnings when > 5% of total links', () => {
    const links = Array.from({ length: 20 }, (_, i) => ({
      source: 2, target: 1,
      context: 'contextual',
      anchor: i < 2 ? 'click here' : `unique-anchor-${i}`,
      weight: 1,
    }));
    component.topology = {
      nodes: [
        { id: 1, title: 'A', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 20, out_degree: 0 },
        { id: 2, title: 'B', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 0, out_degree: 20 },
      ],
      links,
    };

    (component as any)._computeQuality();

    // 2 out of 20 = 10% — should trigger warning
    expect(component.anchorWarnings.length).toBeGreaterThan(0);
    expect(component.anchorWarnings[0].anchor).toBe('click here');
    expect(component.anchorWarnings[0].pct).toBe(10);
  });

  it('should sort pageQualityRows worst-first', () => {
    component.topology = {
      nodes: [
        { id: 1, title: 'Low Quality', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 3, out_degree: 0 },
        { id: 2, title: 'High Quality', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 2, out_degree: 0 },
        { id: 3, title: 'Source',       type: 'thread', silo_id: 0, pagerank: 0, in_degree: 0, out_degree: 5 },
      ],
      links: [
        { source: 3, target: 1, context: 'isolated',    anchor: '', weight: 1 },
        { source: 3, target: 1, context: 'isolated',    anchor: '', weight: 1 },
        { source: 3, target: 1, context: 'contextual',  anchor: '', weight: 1 },
        { source: 3, target: 2, context: 'contextual',  anchor: '', weight: 1 },
        { source: 3, target: 2, context: 'contextual',  anchor: '', weight: 1 },
      ],
    };

    (component as any)._computeQuality();

    expect(component.pageQualityRows.length).toBe(2);
    // Low Quality page has 1/3 contextual (33%) — comes first (worst)
    expect(component.pageQualityRows[0].title).toBe('Low Quality');
    expect(component.pageQualityRows[0].qualityLabel).toBe('Low');
    // High Quality page has 2/2 contextual (100%)
    expect(component.pageQualityRows[1].title).toBe('High Quality');
    expect(component.pageQualityRows[1].qualityLabel).toBe('High');
  });

  it('should populate isolatedLinks only with isolated edges', () => {
    component.topology = {
      nodes: [
        { id: 1, title: 'Target', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 2, out_degree: 0 },
        { id: 2, title: 'Source', type: 'thread', silo_id: 0, pagerank: 0, in_degree: 0, out_degree: 2 },
      ],
      links: [
        { source: 2, target: 1, context: 'isolated',   anchor: 'bare link', weight: 1 },
        { source: 2, target: 1, context: 'contextual', anchor: 'good link', weight: 1 },
      ],
    };

    (component as any)._computeQuality();

    expect(component.isolatedLinks.length).toBe(1);
    expect(component.isolatedLinks[0].anchor).toBe('bare link');
    expect(component.isolatedLinks[0].srcTitle).toBe('Source');
    expect(component.isolatedLinks[0].tgtTitle).toBe('Target');
  });
});
