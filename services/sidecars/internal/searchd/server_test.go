package searchd

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

// buildServer makes a Server backed by a fresh temp Bleve index.
func buildServer(t *testing.T) *Server {
	t.Helper()
	return &Server{
		dataDir:   t.TempDir(),
		logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		startedAt: time.Now(),
	}
}

func indexDocs(t *testing.T, s *Server, docs ...*sidecarsv1.SearchdDocument) {
	t.Helper()
	if _, err := s.Index(context.Background(), &sidecarsv1.SearchdIndexRequest{Documents: docs}); err != nil {
		t.Fatalf("Index: %v", err)
	}
}

func TestIndexAndSearch_RanksMatch(t *testing.T) {
	s := buildServer(t)
	t.Cleanup(s.Idle)
	indexDocs(t, s,
		&sidecarsv1.SearchdDocument{
			Id: "autoissue:1", Kind: "autoissue",
			Title: "null pointer in pipeline scoring",
			Body:  "Trap: a nil embedding slips past the guard. Fix shape: validate before scoring.",
			Area:  "backend/apps/pipeline/services",
		},
		&sidecarsv1.SearchdDocument{
			Id: "autoissue:2", Kind: "autoissue",
			Title: "loki log volume spike",
			Body:  "Trap: a chatty logger floods loki. Fix shape: sample debug logs.",
			Area:  "backend/apps/observability",
		},
	)
	res, err := s.Search(context.Background(), &sidecarsv1.SearchdQueryRequest{Query: "pipeline scoring"})
	if err != nil {
		t.Fatalf("Search: %v", err)
	}
	if len(res.Hits) == 0 {
		t.Fatal("expected at least one hit for 'pipeline scoring'")
	}
	if res.Hits[0].Id != "autoissue:1" {
		t.Fatalf("top hit: got %q, want autoissue:1", res.Hits[0].Id)
	}
	if res.Hits[0].Score <= 0 {
		t.Fatalf("expected positive BM25 score, got %v", res.Hits[0].Score)
	}
}

func TestSearch_AreaFilter(t *testing.T) {
	s := buildServer(t)
	t.Cleanup(s.Idle)
	indexDocs(t, s,
		&sidecarsv1.SearchdDocument{Id: "a:1", Kind: "autoissue", Title: "guard fix",
			Body: "validate input", Area: "backend/apps/pipeline/services"},
		&sidecarsv1.SearchdDocument{Id: "a:2", Kind: "autoissue", Title: "guard fix",
			Body: "validate input", Area: "backend/apps/observability"},
	)
	res, err := s.Search(context.Background(), &sidecarsv1.SearchdQueryRequest{
		Query: "validate", Area: "backend/apps/pipeline",
	})
	if err != nil {
		t.Fatalf("Search: %v", err)
	}
	for _, h := range res.Hits {
		if h.Id == "a:2" {
			t.Fatal("area filter should have excluded the observability doc")
		}
	}
	if len(res.Hits) != 1 || res.Hits[0].Id != "a:1" {
		t.Fatalf("area filter: got %d hits, want 1 (a:1)", len(res.Hits))
	}
}

func TestDelete_RemovesFromIndex(t *testing.T) {
	s := buildServer(t)
	t.Cleanup(s.Idle)
	indexDocs(t, s, &sidecarsv1.SearchdDocument{
		Id: "x:1", Kind: "snapshot", Title: "evidence", Body: "find me",
	})
	if _, err := s.Delete(context.Background(), &sidecarsv1.SearchdDeleteRequest{Ids: []string{"x:1"}}); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	res, err := s.Search(context.Background(), &sidecarsv1.SearchdQueryRequest{Query: "find"})
	if err != nil {
		t.Fatalf("Search: %v", err)
	}
	if res.Total != 0 {
		t.Fatalf("expected 0 hits after delete, got %d", res.Total)
	}
}

func TestSearch_EmptyQueryRejected(t *testing.T) {
	s := buildServer(t)
	t.Cleanup(s.Idle)
	if _, err := s.Search(context.Background(), &sidecarsv1.SearchdQueryRequest{Query: ""}); err == nil {
		t.Fatal("empty query should be rejected")
	}
}

func TestProtoTotalCapsOverflow(t *testing.T) {
	if got := protoTotal(^uint64(0)); got != int64(^uint64(0)>>1) {
		t.Fatalf("overflow total: got %d, want max int64", got)
	}
	if got := protoTotal(42); got != 42 {
		t.Fatalf("small total: got %d, want 42", got)
	}
}

func TestIdle_ReleasesAndReopens(t *testing.T) {
	s := buildServer(t)
	indexDocs(t, s, &sidecarsv1.SearchdDocument{Id: "y:1", Kind: "autoissue", Title: "t", Body: "reopen me"})
	s.Idle() // close the index
	// A search after Idle must reopen the index and still find the doc.
	res, err := s.Search(context.Background(), &sidecarsv1.SearchdQueryRequest{Query: "reopen"})
	if err != nil {
		t.Fatalf("Search after Idle: %v", err)
	}
	if res.Total == 0 {
		t.Fatal("index should persist across Idle and reopen")
	}
	s.Idle()
}

func TestHealth_ReturnsServing(t *testing.T) {
	s := buildServer(t)
	t.Cleanup(s.Idle)
	got, err := s.Health(context.Background(), &sidecarsv1.Empty{})
	if err != nil {
		t.Fatalf("Health: %v", err)
	}
	if got.Status != sidecarsv1.HealthStatus_HEALTH_SERVING {
		t.Fatalf("status: got %v, want HEALTH_SERVING", got.Status)
	}
	if got.Service != ServiceName {
		t.Fatalf("service: got %q, want %q", got.Service, ServiceName)
	}
}

func TestServerImplementsIdler(t *testing.T) {
	var _ idle.Idler = &Server{}
}
