package snapshotd

// Strict-TDD Red test for paper-trail #564 / #578 — swap snapshotd storage
// from JSON-Lines to Parquet so the row-preview UI and external readers can
// open the same file with arrow/parquet tools without a custom JSON-Lines
// decoder. The contract shape (one row per record, 64 KiB row cap, schema
// versioning, 25 MB per-snapshot cap) stays identical; only the wire format
// changes.
//
// This file asserts:
//   1. CreateSnapshot writes a Parquet file (4-byte "PAR1" magic at both ends).
//   2. The file extension is ".parquet" (.jsonl is no longer accepted).
//   3. The Snapshot metadata records the .parquet path so GetSnapshot can
//      surface it back to the row preview reader.
//
// Source: Apache Parquet format spec — https://parquet.apache.org/docs/file-format/
// "Files have a 4-byte magic number PAR1 at the start and end".

import (
	"bytes"
	"context"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"go.etcd.io/bbolt"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
)

func newTestServer(t *testing.T) *Server {
	t.Helper()
	tmp := t.TempDir()
	dbPath := filepath.Join(tmp, "snapshotd.db")
	db, err := bbolt.Open(dbPath, 0o600, nil)
	if err != nil {
		t.Fatalf("open bolt: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	return newServer(Options{
		Store:   db,
		DataDir: filepath.Join(tmp, "data"),
		Logger:  logger,
	})
}

// TestCreateSnapshot_WritesParquetMagic is the Red test — it expects the
// produced file to start AND end with the PAR1 magic and end in `.parquet`.
// JSON-Lines output (the current implementation) starts with `{` and ends in
// `.jsonl`, so this test fails until CreateSnapshot is rewritten on top of
// parquet-go.
func TestCreateSnapshot_WritesParquetMagic(t *testing.T) {
	s := newTestServer(t)
	resp, err := s.CreateSnapshot(context.Background(), &sidecarsv1.CreateSnapshotRequest{
		IssueId:       1,
		Kind:          sidecarsv1.SnapshotKind_SK_BEFORE,
		Category:      "test",
		SchemaVersion: "v1",
		Rows: []*sidecarsv1.SnapshotRow{
			{PayloadJson: []byte(`{"k":"v"}`)},
		},
	})
	if err != nil {
		t.Fatalf("CreateSnapshot returned error: %v", err)
	}
	if !strings.HasSuffix(resp.GetPath(), ".parquet") {
		t.Fatalf("expected .parquet extension, got %s", resp.GetPath())
	}
	info, err := os.Stat(resp.GetPath())
	if err != nil {
		t.Fatalf("stat snapshot file: %v", err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Fatalf("snapshot file mode: got %o, want 0600", got)
	}
	data, err := os.ReadFile(resp.GetPath())
	if err != nil {
		t.Fatalf("read snapshot file: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("PAR1")) {
		t.Fatalf("expected file to start with PAR1 magic, got %q", string(data[:min(len(data), 16)]))
	}
	if !bytes.HasSuffix(data, []byte("PAR1")) {
		t.Fatalf("expected file to end with PAR1 magic, got %q", string(data[max(0, len(data)-16):]))
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
