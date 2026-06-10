// Package searchd is the Lucene-equivalent full-text index for the repo.
//
// It is built on Bleve — a pure-Go search engine with the same inverted-index
// + BM25 ranking model as Apache Lucene, but with no JVM dependency, so it
// fits the sidecars host's small static-binary footprint. searchd indexes
// AutoIssues, PaperTrail entries, and snapshot evidence so session-start
// lesson lookups and issue searches return RANKED results instead of SQL
// substring matches.
//
// The index is persisted under /var/lib/xf/sidecars/searchd/ and is opened
// (or created) lazily on first use. Under memory pressure the idle tracker
// calls Idle(), which closes the index handle; the next call reopens it.
//
// References:
//   - Bleve docs (blevesearch.com) — inverted index + BM25 scoring.
//   - Robertson & Zaragoza 2009, "The Probabilistic Relevance Framework:
//     BM25 and Beyond" (doi:10.1561/1500000019).
package searchd

import (
	"context"
	"log/slog"
	"math"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/blevesearch/bleve/v2"
	"github.com/blevesearch/bleve/v2/analysis/analyzer/keyword"
	"github.com/blevesearch/bleve/v2/mapping"
	"github.com/blevesearch/bleve/v2/search/query"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

const ServiceName = "searchd"

const defaultLimit = 10

// Server is the gRPC handler. The Bleve index is guarded by mu and opened
// lazily so Idle() can release it under memory pressure.
type Server struct {
	sidecarsv1.UnimplementedSearchdServer
	dataDir   string
	logger    *slog.Logger
	startedAt time.Time

	mu    sync.Mutex
	index bleve.Index
}

// Register wires the server onto the shared gRPC server + idle tracker.
func Register(
	grpcSrv *grpc.Server,
	tracker *idle.Tracker,
	logger *slog.Logger,
	dataDir string,
) *Server {
	s := &Server{
		dataDir:   dataDir,
		logger:    logger.With("service", ServiceName),
		startedAt: time.Now(),
	}
	sidecarsv1.RegisterSearchdServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityMedium)
	return s
}

// Idle releases the Bleve index handle so its caches return memory when the
// service is not being used. The next call to ensureIndex reopens it.
func (s *Server) Idle() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.index != nil {
		_ = s.index.Close()
		s.index = nil
	}
}

// ensureIndex opens the persisted index, creating it on first use. Caller must
// hold s.mu.
func (s *Server) ensureIndex() (bleve.Index, error) {
	if s.index != nil {
		return s.index, nil
	}
	path := filepath.Join(s.dataDir, "index.bleve")
	if err := os.MkdirAll(s.dataDir, 0o750); err != nil {
		return nil, err
	}
	idx, err := bleve.Open(path)
	if err == bleve.ErrorIndexPathDoesNotExist {
		idx, err = bleve.New(path, buildIndexMapping())
	}
	if err != nil {
		return nil, err
	}
	s.index = idx
	return idx, nil
}

// buildIndexMapping indexes `title` and `body` with the default analyzer
// (tokenized, stemmed — good for free-text BM25 search) but `area` and `kind`
// with the keyword analyzer (stored as a single untokenized term) so an exact
// kind filter and an area PREFIX filter work on the full path string.
func buildIndexMapping() mapping.IndexMapping {
	kw := bleve.NewTextFieldMapping()
	kw.Analyzer = keyword.Name

	doc := bleve.NewDocumentMapping()
	doc.AddFieldMappingsAt("area", kw)
	doc.AddFieldMappingsAt("kind", kw)

	im := bleve.NewIndexMapping()
	im.DefaultMapping = doc
	return im
}

// indexedDoc is the flat shape Bleve stores; mirrors the proto Document.
type indexedDoc struct {
	Kind  string   `json:"kind"`
	Title string   `json:"title"`
	Body  string   `json:"body"`
	Area  string   `json:"area"`
	Tags  []string `json:"tags"`
}

// Index upserts a batch of documents (idempotent by id).
func (s *Server) Index(_ context.Context, req *sidecarsv1.SearchdIndexRequest) (*sidecarsv1.Ack, error) {
	if len(req.GetDocuments()) == 0 {
		return &sidecarsv1.Ack{Ok: true, Detail: "no documents"}, nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	idx, err := s.ensureIndex()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "open index: %v", err)
	}
	batch := idx.NewBatch()
	for _, d := range req.GetDocuments() {
		if d.GetId() == "" {
			return nil, status.Error(codes.InvalidArgument, "document id is required")
		}
		if err := batch.Index(d.GetId(), indexedDoc{
			Kind:  d.GetKind(),
			Title: d.GetTitle(),
			Body:  d.GetBody(),
			Area:  d.GetArea(),
			Tags:  d.GetTags(),
		}); err != nil {
			return nil, status.Errorf(codes.Internal, "index %s: %v", d.GetId(), err)
		}
	}
	if err := idx.Batch(batch); err != nil {
		return nil, status.Errorf(codes.Internal, "commit batch: %v", err)
	}
	return &sidecarsv1.Ack{Ok: true, Detail: "indexed"}, nil
}

// Search runs a ranked full-text query with optional kind/area filters.
func (s *Server) Search(_ context.Context, req *sidecarsv1.SearchdQueryRequest) (*sidecarsv1.SearchdResults, error) {
	if req.GetQuery() == "" {
		return nil, status.Error(codes.InvalidArgument, "query is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	idx, err := s.ensureIndex()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "open index: %v", err)
	}
	limit := int(req.GetLimit())
	if limit <= 0 {
		limit = defaultLimit
	}
	searchReq := bleve.NewSearchRequestOptions(s.buildQuery(req), limit, 0, false)
	searchReq.Fields = []string{"kind", "title"}
	searchReq.Highlight = bleve.NewHighlight()
	res, err := idx.Search(searchReq)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "search: %v", err)
	}
	out := &sidecarsv1.SearchdResults{Total: protoTotal(res.Total)}
	for _, hit := range res.Hits {
		out.Hits = append(out.Hits, &sidecarsv1.SearchdHit{
			Id:       hit.ID,
			Kind:     fieldString(hit.Fields, "kind"),
			Title:    fieldString(hit.Fields, "title"),
			Score:    hit.Score,
			Fragment: firstFragment(hit.Fragments),
		})
	}
	return out, nil
}

// buildQuery combines the free-text match with optional kind/area filters.
func (s *Server) buildQuery(req *sidecarsv1.SearchdQueryRequest) query.Query {
	text := bleve.NewMatchQuery(req.GetQuery())
	conj := bleve.NewConjunctionQuery(text)
	if req.GetKind() != "" {
		// kind is a keyword field — match it exactly with a term query.
		kq := bleve.NewTermQuery(req.GetKind())
		kq.SetField("kind")
		conj.AddQuery(kq)
	}
	if req.GetArea() != "" {
		aq := bleve.NewPrefixQuery(req.GetArea())
		aq.SetField("area")
		conj.AddQuery(aq)
	}
	return conj
}

// Delete removes documents by id.
func (s *Server) Delete(_ context.Context, req *sidecarsv1.SearchdDeleteRequest) (*sidecarsv1.Ack, error) {
	if len(req.GetIds()) == 0 {
		return &sidecarsv1.Ack{Ok: true, Detail: "no ids"}, nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	idx, err := s.ensureIndex()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "open index: %v", err)
	}
	batch := idx.NewBatch()
	for _, id := range req.GetIds() {
		batch.Delete(id)
	}
	if err := idx.Batch(batch); err != nil {
		return nil, status.Errorf(codes.Internal, "delete batch: %v", err)
	}
	return &sidecarsv1.Ack{Ok: true, Detail: "deleted"}, nil
}

// Health is the standard liveness probe.
func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

func protoTotal(total uint64) int64 {
	if total > uint64(math.MaxInt64) {
		return math.MaxInt64
	}
	return int64(total)
}

func fieldString(fields map[string]any, key string) string {
	if v, ok := fields[key].(string); ok {
		return v
	}
	return ""
}

func firstFragment(fragments map[string][]string) string {
	for _, frags := range fragments {
		if len(frags) > 0 {
			return frags[0]
		}
	}
	return ""
}

// Compile-time guard: Server satisfies idle.Idler.
var _ idle.Idler = (*Server)(nil)
