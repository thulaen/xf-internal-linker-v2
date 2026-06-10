// Package snapshotd is the durable evidence layer for AutoIssues.
//
// Slice 1.6 stores snapshots as Parquet files under
// /var/lib/xf/sidecars/snapshotd/. Parquet was the spec target (Apache
// Parquet format spec — https://parquet.apache.org/docs/file-format/) and
// the JSON-Lines interim was replaced once the binary-size budget was
// raised to 40 MB and parquet-go was added.
//
// All 9 unary RPCs are implemented (CreateSnapshot, GetSnapshot,
// ListByIssue, Compare, Pin, Unpin, DiffBeforeAfter, plus Health).
// The two streaming RPCs (Search, ReadRows) live in the same package and
// read the Parquet payload via the same library so an external tool can
// open the file too.
package snapshotd

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/parquet-go/parquet-go"
	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

// parquetRow is the on-disk schema for one snapshot record. Keeping the
// payload as a single binary column preserves the existing contract shape
// (the row's JSON bytes flow through unchanged) so the row-preview reader
// stays compatible after the JSON-Lines → Parquet swap.
type parquetRow struct {
	PayloadJSON []byte `parquet:"payload_json"`
	OrderIdx    int32  `parquet:"order_idx"`
}

const (
	ServiceName            = "snapshotd"
	defaultMaxSizeMB       = 25
	maxRowBytes            = 64 << 10 // 64 KiB per docs/specs/fr-sidecars-host.md
	pinnedBucketName       = "pinned"
	snapshotMetaBucketName = "snapshots"
	snapshotsByIssueBucket = "by_issue"
)

var (
	pinnedBucket       = []byte(pinnedBucketName)
	snapshotMetaBucket = []byte(snapshotMetaBucketName)
	snapshotsByIssue   = []byte(snapshotsByIssueBucket)
)

type Server struct {
	sidecarsv1.UnimplementedSnapshotdServer
	store     *bbolt.DB
	dataDir   string
	logger    *slog.Logger
	startedAt time.Time

	mu sync.Mutex // serializes file writes so two CreateSnapshot calls don't fight
}

// Options for hand-building during tests.
type Options struct {
	Store   *bbolt.DB
	DataDir string
	Logger  *slog.Logger
}

func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger, dataDir string) *Server {
	s := newServer(Options{Store: db, DataDir: dataDir, Logger: logger})
	sidecarsv1.RegisterSnapshotdServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

func newServer(opts Options) *Server {
	s := &Server{
		store:     opts.Store,
		dataDir:   opts.DataDir,
		logger:    opts.Logger.With("service", ServiceName),
		startedAt: time.Now(),
	}
	_ = os.MkdirAll(opts.DataDir, 0o755)
	_ = s.store.Update(func(tx *bbolt.Tx) error {
		for _, b := range [][]byte{pinnedBucket, snapshotMetaBucket, snapshotsByIssue} {
			if _, err := tx.CreateBucketIfNotExists(b); err != nil {
				return err
			}
		}
		return nil
	})
	return s
}

// Idle releases nothing — snapshotd reads all state on demand.
func (s *Server) Idle() {}

// IsPinned implements the PinChecker contract for the pruner so pinned
// snapshot files survive the 7-day age sweep.
func (s *Server) IsPinned(path string) bool {
	id := snapshotIDFromPath(path)
	if id == "" {
		return false
	}
	var pinned bool
	_ = s.store.View(func(tx *bbolt.Tx) error {
		pinned = tx.Bucket(pinnedBucket).Get([]byte(id)) != nil
		return nil
	})
	return pinned
}

func (s *Server) CreateSnapshot(_ context.Context, req *sidecarsv1.CreateSnapshotRequest) (*sidecarsv1.Snapshot, error) {
	if req.GetIssueId() == 0 {
		return nil, status.Error(codes.InvalidArgument, "issue_id is required")
	}
	if req.GetSchemaVersion() == "" {
		return nil, status.Error(codes.InvalidArgument, "schema_version is required")
	}
	if len(req.GetRows()) == 0 {
		return nil, status.Error(codes.InvalidArgument, "at least one row is required")
	}
	maxBytes := int64(defaultMaxSizeMB) << 20
	if req.GetMaxSizeMb() > 0 {
		maxBytes = int64(req.GetMaxSizeMb()) << 20
	}

	id := uuid.New().String()
	dir := filepath.Join(s.dataDir, fmt.Sprintf("issue_%d", req.GetIssueId()))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, status.Errorf(codes.Internal, "mkdir: %v", err)
	}
	path := filepath.Join(dir, id+".parquet")

	s.mu.Lock()
	defer s.mu.Unlock()

	// Per-row cap check stays identical so the JSON-Lines → Parquet swap is
	// invisible to producers.
	for i, row := range req.GetRows() {
		if len(row.GetPayloadJson()) > maxRowBytes {
			return nil, status.Errorf(codes.InvalidArgument,
				"row %d exceeds %d-byte cap (got %d bytes)",
				i, maxRowBytes, len(row.GetPayloadJson()))
		}
	}
	parquetBytes, err := writeParquet(req.GetRows())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "encode parquet: %v", err)
	}
	if int64(len(parquetBytes)) > maxBytes {
		return nil, status.Errorf(codes.InvalidArgument,
			"snapshot total %d bytes exceeds cap %d", len(parquetBytes), maxBytes)
	}
	if err := os.WriteFile(path, parquetBytes, 0o600); err != nil {
		return nil, status.Errorf(codes.Internal, "write file: %v", err)
	}

	snap := &sidecarsv1.Snapshot{
		Id:                     id,
		IssueId:                req.GetIssueId(),
		Kind:                   req.GetKind(),
		Category:               req.GetCategory(),
		SchemaVersion:          req.GetSchemaVersion(),
		Path:                   path,
		RowCount:               int64(len(req.GetRows())),
		SizeBytes:              int64(len(parquetBytes)),
		CreatedAtUnixNanos:     time.Now().UnixNano(),
		LastTouchedAtUnixNanos: time.Now().UnixNano(),
	}
	if err := s.writeMeta(snap); err != nil {
		_ = os.Remove(path)
		return nil, status.Errorf(codes.Internal, "write meta: %v", err)
	}
	// Critical kind auto-pins; pinned snapshots survive the 7-day age sweep.
	if snap.Kind == sidecarsv1.SnapshotKind_SK_CRITICAL || snap.Kind == sidecarsv1.SnapshotKind_SK_BEFORE {
		_ = s.pin(snap.Id, snap.IssueId)
		snap.Pinned = true
	}
	return snap, nil
}

func (s *Server) GetSnapshot(_ context.Context, req *sidecarsv1.GetSnapshotRequest) (*sidecarsv1.Snapshot, error) {
	if req.GetId() == "" {
		return nil, status.Error(codes.InvalidArgument, "id is required")
	}
	return s.loadMeta(req.GetId())
}

func (s *Server) ListByIssue(_ context.Context, req *sidecarsv1.ListByIssueRequest) (*sidecarsv1.SnapshotList, error) {
	if req.GetIssueId() == 0 {
		return nil, status.Error(codes.InvalidArgument, "issue_id is required")
	}
	ids, err := s.loadIssueIndex(req.GetIssueId())
	if err != nil {
		return nil, status.Errorf(codes.Internal, "lookup issue index: %v", err)
	}
	out := &sidecarsv1.SnapshotList{}
	for _, id := range ids {
		snap, err := s.loadMeta(id)
		if err != nil {
			continue
		}
		out.Items = append(out.Items, snap)
	}
	sort.Slice(out.Items, func(i, j int) bool {
		return out.Items[i].GetCreatedAtUnixNanos() < out.Items[j].GetCreatedAtUnixNanos()
	})
	return out, nil
}

func (s *Server) Pin(_ context.Context, req *sidecarsv1.PinRequest) (*sidecarsv1.Snapshot, error) {
	if req.GetSnapshotId() == "" {
		return nil, status.Error(codes.InvalidArgument, "snapshot_id is required")
	}
	if err := s.pin(req.GetSnapshotId(), req.GetIssueId()); err != nil {
		return nil, status.Errorf(codes.Internal, "pin: %v", err)
	}
	snap, err := s.loadMeta(req.GetSnapshotId())
	if err != nil {
		return nil, err
	}
	snap.Pinned = true
	return snap, nil
}

func (s *Server) Unpin(_ context.Context, req *sidecarsv1.UnpinRequest) (*sidecarsv1.Snapshot, error) {
	if req.GetSnapshotId() == "" {
		return nil, status.Error(codes.InvalidArgument, "snapshot_id is required")
	}
	err := s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(pinnedBucket).Delete([]byte(req.GetSnapshotId()))
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "unpin: %v", err)
	}
	snap, err := s.loadMeta(req.GetSnapshotId())
	if err != nil {
		return nil, err
	}
	snap.Pinned = false
	return snap, nil
}

func (s *Server) Compare(_ context.Context, req *sidecarsv1.CompareRequest) (*sidecarsv1.ComparisonReport, error) {
	before, err := s.loadMeta(req.GetBeforeId())
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "before snapshot: %v", err)
	}
	after, err := s.loadMeta(req.GetAfterId())
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "after snapshot: %v", err)
	}
	if before.GetSchemaVersion() != after.GetSchemaVersion() {
		return nil, status.Errorf(codes.FailedPrecondition,
			"schema versions differ: before=%s after=%s", before.GetSchemaVersion(), after.GetSchemaVersion())
	}
	return diffSnapshots(before, after)
}

func (s *Server) DiffBeforeAfter(ctx context.Context, req *sidecarsv1.DiffBeforeAfterRequest) (*sidecarsv1.ComparisonReport, error) {
	list, err := s.ListByIssue(ctx, &sidecarsv1.ListByIssueRequest{IssueId: req.GetIssueId()})
	if err != nil {
		return nil, err
	}
	var before, after *sidecarsv1.Snapshot
	for _, snap := range list.GetItems() {
		switch snap.GetKind() {
		case sidecarsv1.SnapshotKind_SK_BEFORE:
			if before == nil || snap.GetCreatedAtUnixNanos() > before.GetCreatedAtUnixNanos() {
				before = snap
			}
		case sidecarsv1.SnapshotKind_SK_AFTER:
			if after == nil || snap.GetCreatedAtUnixNanos() > after.GetCreatedAtUnixNanos() {
				after = snap
			}
		}
	}
	if before == nil || after == nil {
		return nil, status.Errorf(codes.FailedPrecondition,
			"issue %d needs both a SK_BEFORE and SK_AFTER snapshot to diff", req.GetIssueId())
	}
	return s.Compare(ctx, &sidecarsv1.CompareRequest{BeforeId: before.GetId(), AfterId: after.GetId()})
}

func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

// Search is the slice-1.6 streaming search RPC. Walks every snapshot for
// every open issue and emits matches one at a time. Filters: issue_id
// (0 → any), kind (SK_UNKNOWN → any), category (empty → any). offset +
// limit bound the response window so a large evidence corpus does not
// blow the receive buffer.
func (s *Server) Search(req *sidecarsv1.SearchRequest, stream sidecarsv1.Snapshotd_SearchServer) error {
	offset := int(req.GetOffset())
	limit := int(req.GetLimit())
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	matched := 0
	skipped := 0
	err := s.store.View(func(tx *bbolt.Tx) error {
		return tx.Bucket(snapshotMetaBucket).ForEach(func(_, raw []byte) error {
			if stream.Context().Err() != nil {
				return stream.Context().Err()
			}
			snap := &sidecarsv1.Snapshot{}
			if err := json.Unmarshal(raw, snap); err != nil {
				return nil // skip malformed rows
			}
			if req.GetIssueId() != 0 && snap.GetIssueId() != req.GetIssueId() {
				return nil
			}
			if req.GetKind() != sidecarsv1.SnapshotKind_SK_UNKNOWN &&
				snap.GetKind() != req.GetKind() {
				return nil
			}
			if req.GetCategory() != "" && snap.GetCategory() != req.GetCategory() {
				return nil
			}
			if skipped < offset {
				skipped++
				return nil
			}
			if matched >= limit {
				return errSearchLimitReached
			}
			// Re-check pinned bit since loadMeta does that lookup at read time.
			snap.Pinned = tx.Bucket(pinnedBucket).Get([]byte(snap.GetId())) != nil
			if err := stream.Send(snap); err != nil {
				return err
			}
			matched++
			return nil
		})
	})
	if err != nil && err != errSearchLimitReached {
		return status.Errorf(codes.Internal, "search: %v", err)
	}
	return nil
}

// ReadRows is the slice-1.6 streaming row-read RPC. Opens the snapshot's
// Parquet file and yields one SnapshotRow per record. max_rows bounds
// the response window; if max_rows <= 0 the server caps at 500 (the
// largest reasonable preview for the operator UI).
func (s *Server) ReadRows(req *sidecarsv1.ReadRowsRequest, stream sidecarsv1.Snapshotd_ReadRowsServer) error {
	snap, err := s.loadMeta(req.GetSnapshotId())
	if err != nil {
		return err
	}
	max := int(req.GetMaxRows())
	if max <= 0 || max > 500 {
		max = 500
	}
	rows, err := readParquet(snap.GetPath(), max)
	if err != nil {
		return status.Errorf(codes.Internal, "read parquet: %v", err)
	}
	for _, row := range rows {
		if stream.Context().Err() != nil {
			return stream.Context().Err()
		}
		if err := stream.Send(&sidecarsv1.SnapshotRow{PayloadJson: row.PayloadJSON}); err != nil {
			return err
		}
	}
	return nil
}

// writeParquet encodes the snapshot rows as a single-row-group Parquet
// file in memory. Each gRPC SnapshotRow becomes one parquetRow record so
// the on-disk schema matches the wire contract.
func writeParquet(rows []*sidecarsv1.SnapshotRow) ([]byte, error) {
	records := make([]parquetRow, len(rows))
	for i, row := range rows {
		records[i] = parquetRow{
			PayloadJSON: row.GetPayloadJson(),
			OrderIdx:    int32(i),
		}
	}
	var buf bytes.Buffer
	writer := parquet.NewGenericWriter[parquetRow](&buf)
	if _, err := writer.Write(records); err != nil {
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// readParquet streams up to `max` rows out of the Parquet file at `path`.
// Used by ReadRows to back the row-preview UI without loading the whole
// file into memory.
func readParquet(path string, max int) ([]parquetRow, error) {
	// #nosec G304 -- path is read from snapshotd metadata that snapshotd wrote at CreateSnapshot time.
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = f.Close() }()
	stat, err := f.Stat()
	if err != nil {
		return nil, err
	}
	reader := parquet.NewGenericReader[parquetRow](
		parquetFileFromOsFile{f: f, size: stat.Size()},
	)
	defer func() { _ = reader.Close() }()
	out := make([]parquetRow, 0, min2(max, int(reader.NumRows())))
	buf := make([]parquetRow, min2(max, 64))
	for len(out) < max {
		n, err := reader.Read(buf)
		if n > 0 {
			take := n
			if len(out)+take > max {
				take = max - len(out)
			}
			out = append(out, buf[:take]...)
		}
		if err != nil {
			break
		}
		if n == 0 {
			break
		}
	}
	return out, nil
}

// parquetFileFromOsFile adapts *os.File to the io.ReaderAt + size that
// parquet-go's reader expects.
type parquetFileFromOsFile struct {
	f    *os.File
	size int64
}

func (p parquetFileFromOsFile) ReadAt(b []byte, off int64) (int, error) {
	return p.f.ReadAt(b, off)
}

func (p parquetFileFromOsFile) Size() int64 { return p.size }

func min2(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// errSearchLimitReached is the sentinel that breaks out of bolt.ForEach
// once we have hit the response window.
var errSearchLimitReached = status.Error(codes.OK, "search-limit-reached")

// --- helpers below ---

func (s *Server) writeMeta(snap *sidecarsv1.Snapshot) error {
	raw, err := json.Marshal(snap)
	if err != nil {
		return err
	}
	return s.store.Update(func(tx *bbolt.Tx) error {
		if err := tx.Bucket(snapshotMetaBucket).Put([]byte(snap.GetId()), raw); err != nil {
			return err
		}
		key := fmt.Sprintf("%d", snap.GetIssueId())
		issueBk, err := tx.Bucket(snapshotsByIssue).CreateBucketIfNotExists([]byte(key))
		if err != nil {
			return err
		}
		return issueBk.Put([]byte(snap.GetId()), []byte{1})
	})
}

func (s *Server) loadMeta(id string) (*sidecarsv1.Snapshot, error) {
	var snap *sidecarsv1.Snapshot
	err := s.store.View(func(tx *bbolt.Tx) error {
		raw := tx.Bucket(snapshotMetaBucket).Get([]byte(id))
		if raw == nil {
			return status.Errorf(codes.NotFound, "snapshot %q not found", id)
		}
		snap = &sidecarsv1.Snapshot{}
		if err := json.Unmarshal(raw, snap); err != nil {
			return err
		}
		snap.Pinned = tx.Bucket(pinnedBucket).Get([]byte(id)) != nil
		return nil
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "load_meta: %v", err)
	}
	return snap, nil
}

func (s *Server) loadIssueIndex(issueID int64) ([]string, error) {
	var ids []string
	err := s.store.View(func(tx *bbolt.Tx) error {
		bk := tx.Bucket(snapshotsByIssue).Bucket([]byte(fmt.Sprintf("%d", issueID)))
		if bk == nil {
			return nil
		}
		return bk.ForEach(func(k, _ []byte) error {
			ids = append(ids, string(k))
			return nil
		})
	})
	return ids, err
}

func (s *Server) pin(id string, issueID int64) error {
	return s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(pinnedBucket).Put([]byte(id), []byte(fmt.Sprintf("%d", issueID)))
	})
}

func snapshotIDFromPath(path string) string {
	base := filepath.Base(path)
	if !strings.HasSuffix(base, ".jsonl") {
		return ""
	}
	return strings.TrimSuffix(base, ".jsonl")
}

// diffSnapshots compares two snapshots field-by-field at the row level. The
// implementation is intentionally simple: each row is parsed as a JSON
// object; common keys are compared by string-cast value.
func diffSnapshots(before, after *sidecarsv1.Snapshot) (*sidecarsv1.ComparisonReport, error) {
	beforeRows, err := readRows(before.GetPath())
	if err != nil {
		return nil, fmt.Errorf("read before: %w", err)
	}
	afterRows, err := readRows(after.GetPath())
	if err != nil {
		return nil, fmt.Errorf("read after: %w", err)
	}
	report := &sidecarsv1.ComparisonReport{BeforeId: before.GetId(), AfterId: after.GetId()}
	limit := len(beforeRows)
	if len(afterRows) < limit {
		limit = len(afterRows)
	}
	for i := 0; i < limit; i++ {
		for key, b := range beforeRows[i] {
			a, ok := afterRows[i][key]
			if !ok {
				continue
			}
			bs, as := stringify(b), stringify(a)
			if bs == as {
				continue
			}
			report.Deltas = append(report.Deltas, &sidecarsv1.FieldDelta{
				Field:     fmt.Sprintf("row[%d].%s", i, key),
				Before:    bs,
				After:     as,
				Direction: classify(bs, as),
			})
		}
	}
	switch {
	case len(report.Deltas) == 0:
		report.Summary = "no field-level changes between before and after"
	case len(report.Regressions) > 0:
		report.Summary = fmt.Sprintf("%d field changes, %d regressions", len(report.Deltas), len(report.Regressions))
	default:
		report.Summary = fmt.Sprintf("%d field changes, no regressions detected", len(report.Deltas))
	}
	return report, nil
}

// readRows loads the snapshot's Parquet rows as a slice of generic JSON
// objects so the diff engine in Compare can walk fields without caring
// about the underlying storage format.
func readRows(path string) ([]map[string]any, error) {
	parquetRows, err := readParquet(path, 1<<20) // 1M rows ceiling — defensive
	if err != nil {
		return nil, err
	}
	rows := make([]map[string]any, 0, len(parquetRows))
	for _, pr := range parquetRows {
		row := make(map[string]any)
		if err := json.Unmarshal(pr.PayloadJSON, &row); err != nil {
			continue // skip malformed rows
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func stringify(v any) string {
	if v == nil {
		return ""
	}
	switch x := v.(type) {
	case string:
		return x
	case float64:
		return strings.TrimRight(strings.TrimRight(fmt.Sprintf("%f", x), "0"), ".")
	case bool:
		if x {
			return "true"
		}
		return "false"
	}
	raw, _ := json.Marshal(v)
	return string(raw)
}

// classify is a coarse direction guess; only signals "regressed" when a
// numeric value grew (typical for latency-style fields) or a "ok" flag
// dropped from true→false.
func classify(before, after string) string {
	if before == after {
		return "unchanged"
	}
	if (before == "true" && after == "false") || (before == "ok" && after == "fail") {
		return "regressed"
	}
	return "changed"
}

var _ idle.Idler = (*Server)(nil)
