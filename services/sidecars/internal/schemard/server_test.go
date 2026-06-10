package schemard

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"math"
	"path/filepath"
	"testing"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

// buildServer spins up a Server with a fresh temp Bolt and a quiet idle
// tracker. Real Register requires a *grpc.Server which we don't need for
// in-process method calls, so we construct the Server directly.
func buildServer(t *testing.T) *Server {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "state.db")
	db, err := bbolt.Open(dbPath, 0o600, &bbolt.Options{Timeout: time.Second})
	if err != nil {
		t.Fatalf("bolt open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	s := &Server{
		store:     db,
		logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		startedAt: time.Now(),
	}
	if err := s.ensureRootBucket(); err != nil {
		t.Fatalf("ensure root bucket: %v", err)
	}
	return s
}

func TestRegister_FirstVersionIsOne(t *testing.T) {
	s := buildServer(t)
	got, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject:    "snapshotd.snapshot.v1",
		SchemaJson: `{"fields":[{"name":"id"},{"name":"kind"}]}`,
	})
	if err != nil {
		t.Fatalf("Register: %v", err)
	}
	if got.Version != 1 {
		t.Fatalf("version: got %d, want 1", got.Version)
	}
	if got.Subject != "snapshotd.snapshot.v1" {
		t.Fatalf("subject: got %q", got.Subject)
	}
}

func TestRegister_VersionsIncrement(t *testing.T) {
	s := buildServer(t)
	for i := 1; i <= 3; i++ {
		got, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
			Subject:    "subj",
			SchemaJson: `{"fields":[{"name":"a"}]}`,
		})
		if err != nil {
			t.Fatalf("Register #%d: %v", i, err)
		}
		if int(got.Version) != i {
			t.Fatalf("version #%d: got %d, want %d", i, got.Version, i)
		}
	}
}

func TestRegister_RejectsVersionLimitOverflow(t *testing.T) {
	s := buildServer(t)
	err := s.store.Update(func(tx *bbolt.Tx) error {
		root := tx.Bucket(subjectsBucket)
		bk, err := root.CreateBucketIfNotExists([]byte("subj"))
		if err != nil {
			return err
		}
		raw, err := json.Marshal(&sidecarsv1.SchemaVersion{
			Subject:    "subj",
			Version:    math.MaxInt32,
			SchemaJson: `{"fields":[{"name":"a"}]}`,
		})
		if err != nil {
			return err
		}
		return bk.Put([]byte{0x7f, 0xff, 0xff, 0xff}, raw)
	})
	if err != nil {
		t.Fatalf("seed max version: %v", err)
	}
	_, err = s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject:    "subj",
		SchemaJson: `{"fields":[{"name":"a"}]}`,
	})
	if err == nil {
		t.Fatal("registering after max int32 version should fail")
	}
	if st, _ := status.FromError(err); st.Code() != codes.ResourceExhausted {
		t.Fatalf("error code: got %v, want ResourceExhausted", st.Code())
	}
}

func TestRegister_RequireBackwardCompat_RejectsFieldRemoval(t *testing.T) {
	s := buildServer(t)
	_, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject:    "subj",
		SchemaJson: `{"fields":[{"name":"a"},{"name":"b"}]}`,
	})
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	_, err = s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject:               "subj",
		SchemaJson:            `{"fields":[{"name":"a"}]}`, // removes "b"
		RequireBackwardCompat: true,
	})
	if err == nil {
		t.Fatal("removal of required field should fail under require_backward_compat")
	}
	if st, _ := status.FromError(err); st.Code() != codes.FailedPrecondition {
		t.Fatalf("error code: got %v, want FailedPrecondition", st.Code())
	}
}

func TestLatest_ReturnsHighestVersion(t *testing.T) {
	s := buildServer(t)
	for _, schema := range []string{
		`{"fields":[{"name":"a"}]}`,
		`{"fields":[{"name":"a"},{"name":"b"}]}`,
		`{"fields":[{"name":"a"},{"name":"b"},{"name":"c"}]}`,
	} {
		if _, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
			Subject: "subj", SchemaJson: schema,
		}); err != nil {
			t.Fatalf("Register: %v", err)
		}
	}
	got, err := s.Latest(context.Background(), &sidecarsv1.LatestRequest{Subject: "subj"})
	if err != nil {
		t.Fatalf("Latest: %v", err)
	}
	if got.Version != 3 {
		t.Fatalf("latest version: got %d, want 3", got.Version)
	}
}

func TestGet_RejectsNonPositiveVersion(t *testing.T) {
	s := buildServer(t)
	if _, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject:    "subj",
		SchemaJson: `{"fields":[{"name":"a"}]}`,
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	_, err := s.Get(context.Background(), &sidecarsv1.GetSchemaRequest{
		Subject: "subj",
		Version: 0,
	})
	if err == nil {
		t.Fatal("version 0 should fail")
	}
	if st, _ := status.FromError(err); st.Code() != codes.InvalidArgument {
		t.Fatalf("error code: got %v, want InvalidArgument", st.Code())
	}
}

func TestCheckCompat_NoPriorVersionIsCompatible(t *testing.T) {
	s := buildServer(t)
	got, err := s.CheckCompat(context.Background(), &sidecarsv1.CheckCompatRequest{
		Subject:             "fresh",
		CandidateSchemaJson: `{"fields":[{"name":"a"}]}`,
		Level:               sidecarsv1.CompatLevel_COMP_BACKWARD,
	})
	if err != nil {
		t.Fatalf("CheckCompat: %v", err)
	}
	if !got.Compatible {
		t.Fatal("first version of a subject must be compatible")
	}
}

func TestCheckCompat_Forward_RejectsAddedField(t *testing.T) {
	s := buildServer(t)
	if _, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject: "subj", SchemaJson: `{"fields":[{"name":"a"}]}`,
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	// FORWARD: an old reader must be able to read new data. Adding "b" breaks
	// that because the old reader does not know "b".
	got, err := s.CheckCompat(context.Background(), &sidecarsv1.CheckCompatRequest{
		Subject:             "subj",
		CandidateSchemaJson: `{"fields":[{"name":"a"},{"name":"b"}]}`,
		Level:               sidecarsv1.CompatLevel_COMP_FORWARD,
	})
	if err != nil {
		t.Fatalf("CheckCompat: %v", err)
	}
	if got.Compatible {
		t.Fatal("adding a field should NOT be forward-compatible")
	}
	if got.CheckedLevel != sidecarsv1.CompatLevel_COMP_FORWARD {
		t.Fatalf("checked level: got %v", got.CheckedLevel)
	}
}

func TestCheckCompat_Forward_AllowsRemovedField(t *testing.T) {
	s := buildServer(t)
	if _, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject: "subj", SchemaJson: `{"fields":[{"name":"a"},{"name":"b"}]}`,
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	got, err := s.CheckCompat(context.Background(), &sidecarsv1.CheckCompatRequest{
		Subject:             "subj",
		CandidateSchemaJson: `{"fields":[{"name":"a"}]}`, // removes "b"
		Level:               sidecarsv1.CompatLevel_COMP_FORWARD,
	})
	if err != nil {
		t.Fatalf("CheckCompat: %v", err)
	}
	if !got.Compatible {
		t.Fatal("removing a field IS forward-compatible (old reader still works)")
	}
}

func TestCheckCompat_Full_RequiresIdenticalFieldSet(t *testing.T) {
	s := buildServer(t)
	if _, err := s.Register(context.Background(), &sidecarsv1.RegisterSchemaRequest{
		Subject: "subj", SchemaJson: `{"fields":[{"name":"a"},{"name":"b"}]}`,
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	// Identical set → FULL compatible.
	ok, err := s.CheckCompat(context.Background(), &sidecarsv1.CheckCompatRequest{
		Subject:             "subj",
		CandidateSchemaJson: `{"fields":[{"name":"a"},{"name":"b"}]}`,
		Level:               sidecarsv1.CompatLevel_COMP_FULL,
	})
	if err != nil {
		t.Fatalf("CheckCompat: %v", err)
	}
	if !ok.Compatible {
		t.Fatal("identical field set must be FULL-compatible")
	}
	// Adding a field breaks FULL (fails forward).
	bad, err := s.CheckCompat(context.Background(), &sidecarsv1.CheckCompatRequest{
		Subject:             "subj",
		CandidateSchemaJson: `{"fields":[{"name":"a"},{"name":"b"},{"name":"c"}]}`,
		Level:               sidecarsv1.CompatLevel_COMP_FULL,
	})
	if err != nil {
		t.Fatalf("CheckCompat: %v", err)
	}
	if bad.Compatible {
		t.Fatal("adding a field must break FULL compatibility")
	}
}

func TestHealth_ReturnsServing(t *testing.T) {
	s := buildServer(t)
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
