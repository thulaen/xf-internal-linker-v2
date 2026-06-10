// Package schemard is the Avro-style schema registry for the sidecars host.
//
// Slice 1.6: snapshotd consults CheckCompat at write time so a new schema
// version cannot break older readers. Schemas are persisted in Bolt under
// /var/lib/xf/sidecars/schemard/state.db.
//
// References:
//   - Apache Avro schema-evolution rules (avro.apache.org/docs/specification/)
//   - bbolt README
package schemard

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"log/slog"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

const ServiceName = "schemard"

var (
	subjectsBucket = []byte("subjects") // sub-bucket per subject keyed by version

	errSubjectRequired = status.Error(codes.InvalidArgument, "subject is required")
	errSchemaRequired  = status.Error(codes.InvalidArgument, "schema_json is required")
)

const maxSchemaVersionUint32 = uint32(1<<31 - 1)

// Server is the gRPC handler.
type Server struct {
	sidecarsv1.UnimplementedSchemardServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time
}

// Register wires the server onto the shared gRPC server + idle tracker.
func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{
		store:     db,
		logger:    logger.With("service", ServiceName),
		startedAt: time.Now(),
	}
	if err := s.ensureRootBucket(); err != nil {
		s.logger.Error("ensure root bucket", "err", err)
	}
	sidecarsv1.RegisterSchemardServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

// Idle has nothing to release — schemard reads all state from Bolt on demand.
func (s *Server) Idle() {}

func (s *Server) ensureRootBucket() error {
	return s.store.Update(func(tx *bbolt.Tx) error {
		_, err := tx.CreateBucketIfNotExists(subjectsBucket)
		return err
	})
}

// Register adds a new schema version. Each subject keeps its versions in a
// sub-bucket keyed by 4-byte big-endian version number. require_backward_compat
// rejects writes that the registered checker would refuse.
func (s *Server) Register(_ context.Context, req *sidecarsv1.RegisterSchemaRequest) (*sidecarsv1.SchemaVersion, error) {
	if req.GetSubject() == "" {
		return nil, errSubjectRequired
	}
	if req.GetSchemaJson() == "" {
		return nil, errSchemaRequired
	}
	if !isJSON(req.GetSchemaJson()) {
		return nil, status.Error(codes.InvalidArgument, "schema_json is not valid JSON")
	}
	var out *sidecarsv1.SchemaVersion
	err := s.store.Update(func(tx *bbolt.Tx) error {
		root := tx.Bucket(subjectsBucket)
		bk, err := root.CreateBucketIfNotExists([]byte(req.GetSubject()))
		if err != nil {
			return err
		}
		nextVersion, _, err := nextVersionFor(bk)
		if err != nil {
			return err
		}
		latest := latestSchema(bk)
		if req.GetRequireBackwardCompat() && latest != "" {
			if !backwardCompatible(latest, req.GetSchemaJson()) {
				return status.Errorf(codes.FailedPrecondition,
					"new schema not backward-compatible with v%d", nextVersion-1)
			}
		}
		out = &sidecarsv1.SchemaVersion{
			Subject:            req.GetSubject(),
			Version:            nextVersion,
			SchemaJson:         req.GetSchemaJson(),
			CreatedAtUnixNanos: time.Now().UnixNano(),
		}
		raw, err := json.Marshal(out)
		if err != nil {
			return err
		}
		return bk.Put(versionKey(nextVersion), raw)
	})
	if err != nil {
		// Preserve gRPC status codes if already wrapped.
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "register: %v", err)
	}
	return out, nil
}

// Get returns the named subject's specified version.
func (s *Server) Get(_ context.Context, req *sidecarsv1.GetSchemaRequest) (*sidecarsv1.SchemaVersion, error) {
	if req.GetSubject() == "" {
		return nil, errSubjectRequired
	}
	if req.GetVersion() <= 0 {
		return nil, status.Error(codes.InvalidArgument, "version must be positive")
	}
	var out *sidecarsv1.SchemaVersion
	err := s.store.View(func(tx *bbolt.Tx) error {
		bk := tx.Bucket(subjectsBucket).Bucket([]byte(req.GetSubject()))
		if bk == nil {
			return status.Errorf(codes.NotFound, "subject %q has no versions", req.GetSubject())
		}
		raw := bk.Get(versionKey(req.GetVersion()))
		if raw == nil {
			return status.Errorf(codes.NotFound, "subject %q version %d not found", req.GetSubject(), req.GetVersion())
		}
		out = &sidecarsv1.SchemaVersion{}
		return json.Unmarshal(raw, out)
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "get: %v", err)
	}
	return out, nil
}

// Latest returns the highest-numbered version for the subject.
func (s *Server) Latest(_ context.Context, req *sidecarsv1.LatestRequest) (*sidecarsv1.SchemaVersion, error) {
	if req.GetSubject() == "" {
		return nil, errSubjectRequired
	}
	var out *sidecarsv1.SchemaVersion
	err := s.store.View(func(tx *bbolt.Tx) error {
		bk := tx.Bucket(subjectsBucket).Bucket([]byte(req.GetSubject()))
		if bk == nil {
			return status.Errorf(codes.NotFound, "subject %q has no versions", req.GetSubject())
		}
		c := bk.Cursor()
		k, v := c.Last()
		if k == nil {
			return status.Errorf(codes.NotFound, "subject %q is empty", req.GetSubject())
		}
		out = &sidecarsv1.SchemaVersion{}
		return json.Unmarshal(v, out)
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "latest: %v", err)
	}
	return out, nil
}

// ListVersions returns all versions for a subject in ascending order.
func (s *Server) ListVersions(_ context.Context, req *sidecarsv1.ListVersionsRequest) (*sidecarsv1.SchemaVersionList, error) {
	if req.GetSubject() == "" {
		return nil, errSubjectRequired
	}
	out := &sidecarsv1.SchemaVersionList{}
	err := s.store.View(func(tx *bbolt.Tx) error {
		bk := tx.Bucket(subjectsBucket).Bucket([]byte(req.GetSubject()))
		if bk == nil {
			return nil
		}
		return bk.ForEach(func(_, v []byte) error {
			sv := &sidecarsv1.SchemaVersion{}
			if err := json.Unmarshal(v, sv); err != nil {
				return err
			}
			out.Items = append(out.Items, sv)
			return nil
		})
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "list_versions: %v", err)
	}
	return out, nil
}

// CheckCompat reports whether a candidate is compatible with the latest
// version. Only BACKWARD (default) is fully implemented this slice; FORWARD
// and FULL return Unimplemented so the caller knows the gap.
func (s *Server) CheckCompat(_ context.Context, req *sidecarsv1.CheckCompatRequest) (*sidecarsv1.CompatReport, error) {
	if req.GetSubject() == "" {
		return nil, errSubjectRequired
	}
	if req.GetCandidateSchemaJson() == "" {
		return nil, status.Error(codes.InvalidArgument, "candidate_schema_json is required")
	}
	level := req.GetLevel()
	if level == sidecarsv1.CompatLevel_COMP_UNKNOWN {
		level = sidecarsv1.CompatLevel_COMP_BACKWARD
	}
	var latest string
	err := s.store.View(func(tx *bbolt.Tx) error {
		bk := tx.Bucket(subjectsBucket).Bucket([]byte(req.GetSubject()))
		if bk == nil {
			return nil
		}
		latest = latestSchema(bk)
		return nil
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "check_compat: %v", err)
	}
	if latest == "" {
		return &sidecarsv1.CompatReport{
			Compatible:   true,
			Detail:       "no prior version exists for this subject; any schema is compatible",
			CheckedLevel: level,
		}, nil
	}
	compatible, detail := evaluateCompat(level, latest, req.GetCandidateSchemaJson())
	return &sidecarsv1.CompatReport{
		Compatible:   compatible,
		Detail:       detail,
		CheckedLevel: level,
	}, nil
}

// evaluateCompat applies the requested compatibility level against the field
// sets of the prior and candidate schemas. Consistent with the registry's
// field-set model (Avro records carry named fields):
//
//	BACKWARD — a new reader can read old data: candidate keeps every old field
//	           (no field removed). new ⊇ old.
//	FORWARD  — an old reader can read new data: candidate adds no field the old
//	           reader does not know. new ⊆ old.
//	FULL     — both: the field sets are identical.
func evaluateCompat(level sidecarsv1.CompatLevel, oldSchema, candidate string) (bool, string) {
	switch level {
	case sidecarsv1.CompatLevel_COMP_FORWARD:
		if forwardCompatible(oldSchema, candidate) {
			return true, "old readers can read data written under the candidate schema"
		}
		return false, "candidate adds fields the prior version's readers do not know"
	case sidecarsv1.CompatLevel_COMP_FULL:
		back := backwardCompatible(oldSchema, candidate)
		fwd := forwardCompatible(oldSchema, candidate)
		if back && fwd {
			return true, "candidate is both backward- and forward-compatible (identical field set)"
		}
		if !back {
			return false, "not backward-compatible: candidate removes fields the prior version requires"
		}
		return false, "not forward-compatible: candidate adds fields the prior version's readers do not know"
	default: // COMP_BACKWARD
		if backwardCompatible(oldSchema, candidate) {
			return true, "candidate schema reads existing data"
		}
		return false, "candidate removes or renames fields the prior version requires"
	}
}

// forwardCompatible reports whether an OLD reader can read data written under
// `candidate`: the candidate must not add any field the old schema lacks.
func forwardCompatible(oldSchema, candidate string) bool {
	oldFields := fieldNames(oldSchema)
	newFields := fieldNames(candidate)
	for f := range newFields {
		if !oldFields[f] {
			return false
		}
	}
	return true
}

// Health is the standard liveness probe.
func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

// versionKey produces a 4-byte big-endian key so cursor.Last returns the
// highest version. (Bolt orders keys lexicographically.)
func versionKey(version int32) []byte {
	v := uint32(version) // #nosec G115 -- schema versions are positive int32 values validated before use.
	return binary.BigEndian.AppendUint32(make([]byte, 0, 4), v)
}

// nextVersionFor inspects the last key in the bucket and returns the next
// version number. The second return is the previous max; useful for compat
// checks. Empty bucket → next=1, prev=0.
func nextVersionFor(bk *bbolt.Bucket) (next int32, prev int32, err error) {
	c := bk.Cursor()
	k, _ := c.Last()
	if k == nil || len(k) != 4 {
		return 1, 0, nil
	}
	prevUint := binary.BigEndian.Uint32(k)
	if prevUint >= maxSchemaVersionUint32 {
		return 0, 0, status.Error(codes.ResourceExhausted, "schema version limit reached")
	}
	prev = int32(prevUint) // #nosec G115 -- prevUint is below max int32 by the guard above.
	next = prev + 1
	return next, prev, nil
}

func latestSchema(bk *bbolt.Bucket) string {
	c := bk.Cursor()
	_, v := c.Last()
	if v == nil {
		return ""
	}
	sv := &sidecarsv1.SchemaVersion{}
	if err := json.Unmarshal(v, sv); err != nil {
		return ""
	}
	return sv.SchemaJson
}

// backwardCompatible reports whether `candidate` can read data written under
// `oldSchema`. The check is the minimum useful one for the slice: every
// required field in oldSchema must still exist (by name) in candidate. Real
// Avro compat is richer; tracked for follow-up.
func backwardCompatible(oldSchema, candidate string) bool {
	oldFields := fieldNames(oldSchema)
	newFields := fieldNames(candidate)
	for f := range oldFields {
		if !newFields[f] {
			return false
		}
	}
	return true
}

// fieldNames is a minimal Avro-schema field extractor: returns the set of
// keys in a top-level JSON object. Avro records are top-level objects with a
// "fields" array; this function handles BOTH a top-level "fields" array AND
// a plain JSON-object schema.
func fieldNames(schema string) map[string]bool {
	out := make(map[string]bool)
	if schema == "" {
		return out
	}
	var generic map[string]any
	if err := json.Unmarshal([]byte(schema), &generic); err != nil {
		return out
	}
	// Avro-style: {"type":"record","fields":[{"name":"a"},{"name":"b"}]}
	if fields, ok := generic["fields"].([]any); ok {
		for _, f := range fields {
			if fmap, ok := f.(map[string]any); ok {
				if name, ok := fmap["name"].(string); ok {
					out[name] = true
				}
			}
		}
		return out
	}
	// Plain JSON-object schema: every top-level key is a field name.
	for k := range generic {
		out[k] = true
	}
	return out
}

func isJSON(s string) bool {
	var generic any
	return json.Unmarshal([]byte(s), &generic) == nil
}

// Compile-time guard: Server satisfies idle.Idler.
var _ idle.Idler = (*Server)(nil)
