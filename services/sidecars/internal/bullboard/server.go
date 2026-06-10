// Package bullboard is the rolling "what is happening now" feed + threshold
// rule engine.
//
// Slice 1.6 implements:
//   - Post / Recent — unary RPCs backed by a bounded in-memory ring buffer
//   - Bolt persistence (so a restart does not lose the last 24 h).
//   - RegisterThreshold / ListThresholds / RemoveThreshold — CRUD on rules.
//   - EvaluateNow — runs one rule against the recent feed without firing.
//   - PromoteToAutoIssue — Acks the request; the caller (Channels bridge in
//     ops_feed) is responsible for actually filing the AutoIssue via
//     apps.auto_issues.api.file_autoissue. bullboard does NOT call governance
//     directly — keeps the boundary clean.
//   - Subscribe — server-streaming live fan-out (added 2026-05-17). Each
//     subscriber gets a 64-buffer channel. A slow subscriber drops messages
//     rather than back-pressuring Post; bounded memory under all loads.
package bullboard

import (
	"context"
	"encoding/json"
	"log/slog"
	"sort"
	"sync"
	"time"

	"github.com/google/uuid"
	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

const (
	ServiceName       = "bullboard"
	maxRecentInMemory = 1000
)

var (
	thresholdsBucket = []byte("thresholds")
	bulletinsBucket  = []byte("bulletins")
)

type Server struct {
	sidecarsv1.UnimplementedBullboardServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time

	mu     sync.RWMutex
	recent []*sidecarsv1.Bulletin // newest first; trimmed to maxRecentInMemory

	subsMu      sync.Mutex
	subscribers map[string]*subscriber // keyed by uuid; live subscribers only
}

// subscriber is one Subscribe-RPC's view into the fan-out. ch is buffered
// (64) so a transient slow consumer does not block Post; if the buffer
// fills, the offending bulletin is dropped for that subscriber and a debug
// log line is emitted.
type subscriber struct {
	ch          chan *sidecarsv1.Bulletin
	eventType   string              // "" = all
	minSeverity sidecarsv1.Severity // SEV_UNKNOWN = all
}

const subscriberBuffer = 64

func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{
		store:       db,
		logger:      logger.With("service", ServiceName),
		startedAt:   time.Now(),
		subscribers: make(map[string]*subscriber),
	}
	_ = s.store.Update(func(tx *bbolt.Tx) error {
		for _, b := range [][]byte{thresholdsBucket, bulletinsBucket} {
			if _, err := tx.CreateBucketIfNotExists(b); err != nil {
				return err
			}
		}
		return nil
	})
	s.warmRecentFromDisk()
	sidecarsv1.RegisterBullboardServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

// Idle drops the in-memory recent cache. Next Recent() rehydrates from Bolt.
func (s *Server) Idle() {
	s.mu.Lock()
	s.recent = nil
	s.mu.Unlock()
}

func (s *Server) Post(_ context.Context, req *sidecarsv1.PostBulletinRequest) (*sidecarsv1.Bulletin, error) {
	if req.GetEventType() == "" {
		return nil, status.Error(codes.InvalidArgument, "event_type is required")
	}
	now := time.Now()
	b := &sidecarsv1.Bulletin{
		Id:                uuid.New().String(),
		EventType:         req.GetEventType(),
		Severity:          req.GetSeverity(),
		Message:           req.GetMessage(),
		ContextJson:       req.GetContextJson(),
		PostedAtUnixNanos: now.UnixNano(),
	}
	raw, err := json.Marshal(b)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		// Key by nanos-then-id so cursor iterates in time order.
		key := bulletinKey(now, b.Id)
		return tx.Bucket(bulletinsBucket).Put(key, raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	s.mu.Lock()
	s.recent = append([]*sidecarsv1.Bulletin{b}, s.recent...)
	if len(s.recent) > maxRecentInMemory {
		s.recent = s.recent[:maxRecentInMemory]
	}
	s.mu.Unlock()
	s.fanOut(b)
	return b, nil
}

// fanOut delivers a freshly-Post()ed bulletin to every live subscriber that
// matches the filter. A full subscriber buffer drops the bulletin for that
// subscriber rather than blocking Post — fast publish wins over guaranteed
// delivery, mirroring the streamd broker's contract.
func (s *Server) fanOut(b *sidecarsv1.Bulletin) {
	s.subsMu.Lock()
	defer s.subsMu.Unlock()
	for id, sub := range s.subscribers {
		if sub.eventType != "" && b.GetEventType() != sub.eventType {
			continue
		}
		if sub.minSeverity != sidecarsv1.Severity_SEV_UNKNOWN &&
			b.GetSeverity() < sub.minSeverity {
			continue
		}
		select {
		case sub.ch <- b:
		default:
			s.logger.Debug("subscriber dropped bulletin (buffer full)",
				"subscriber_id", id, "bulletin_id", b.GetId())
		}
	}
}

// Subscribe is the slice-1.6 streaming live-feed RPC. Registers a
// subscriber with a 64-buffer channel, then loops sending until the
// caller's context cancels. The caller's filter (event_type +
// min_severity) is evaluated at fan-out time so a noisy event_type does
// not waste subscriber buffer slots.
func (s *Server) Subscribe(req *sidecarsv1.SubscribeRequest, stream sidecarsv1.Bullboard_SubscribeServer) error {
	sub := &subscriber{
		ch:          make(chan *sidecarsv1.Bulletin, subscriberBuffer),
		eventType:   req.GetEventType(),
		minSeverity: req.GetMinSeverity(),
	}
	id := uuid.New().String()

	s.subsMu.Lock()
	s.subscribers[id] = sub
	s.subsMu.Unlock()
	s.logger.Info("subscriber attached",
		"subscriber_id", id, "event_type", req.GetEventType(),
		"min_severity", req.GetMinSeverity())

	defer func() {
		s.subsMu.Lock()
		delete(s.subscribers, id)
		s.subsMu.Unlock()
		s.logger.Info("subscriber detached", "subscriber_id", id)
	}()

	ctx := stream.Context()
	for {
		select {
		case <-ctx.Done():
			return nil
		case b := <-sub.ch:
			if err := stream.Send(b); err != nil {
				return err
			}
		}
	}
}

func (s *Server) Recent(_ context.Context, req *sidecarsv1.RecentRequest) (*sidecarsv1.BulletinList, error) {
	if len(s.recent) == 0 {
		s.warmRecentFromDisk()
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	limit := int(req.GetLimit())
	if limit <= 0 || limit > maxRecentInMemory {
		limit = 100
	}
	out := &sidecarsv1.BulletinList{}
	for _, b := range s.recent {
		if len(out.Items) >= limit {
			break
		}
		if req.GetEventType() != "" && b.GetEventType() != req.GetEventType() {
			continue
		}
		if req.GetMinSeverity() != sidecarsv1.Severity_SEV_UNKNOWN && b.GetSeverity() < req.GetMinSeverity() {
			continue
		}
		if req.GetSinceUnixNanos() > 0 && b.GetPostedAtUnixNanos() < req.GetSinceUnixNanos() {
			continue
		}
		out.Items = append(out.Items, b)
	}
	return out, nil
}

func (s *Server) RegisterThreshold(_ context.Context, r *sidecarsv1.ThresholdRule) (*sidecarsv1.ThresholdRule, error) {
	if r.GetEventType() == "" {
		return nil, status.Error(codes.InvalidArgument, "event_type is required")
	}
	if r.GetCount() <= 0 {
		return nil, status.Error(codes.InvalidArgument, "count must be > 0")
	}
	if r.GetWindow() == "" {
		return nil, status.Error(codes.InvalidArgument, "window is required (e.g., 15m)")
	}
	if _, err := time.ParseDuration(r.GetWindow()); err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "window must parse via time.ParseDuration: %v", err)
	}
	if r.GetId() == "" {
		r.Id = "t:" + r.GetEventType() + ":" + time.Now().Format("20060102150405.000000")
	}
	raw, err := json.Marshal(r)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(thresholdsBucket).Put([]byte(r.GetId()), raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	return r, nil
}

func (s *Server) ListThresholds(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.ThresholdRuleList, error) {
	out := &sidecarsv1.ThresholdRuleList{}
	err := s.store.View(func(tx *bbolt.Tx) error {
		return tx.Bucket(thresholdsBucket).ForEach(func(_, v []byte) error {
			r := &sidecarsv1.ThresholdRule{}
			if err := json.Unmarshal(v, r); err != nil {
				return nil
			}
			out.Items = append(out.Items, r)
			return nil
		})
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "list: %v", err)
	}
	return out, nil
}

func (s *Server) RemoveThreshold(_ context.Context, req *sidecarsv1.RemoveThresholdRequest) (*sidecarsv1.Ack, error) {
	if req.GetRuleId() == "" {
		return nil, status.Error(codes.InvalidArgument, "rule_id is required")
	}
	err := s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(thresholdsBucket).Delete([]byte(req.GetRuleId()))
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "delete: %v", err)
	}
	return &sidecarsv1.Ack{Ok: true, Detail: "rule removed"}, nil
}

func (s *Server) EvaluateNow(_ context.Context, req *sidecarsv1.EvaluateNowRequest) (*sidecarsv1.EvaluationReport, error) {
	var rule *sidecarsv1.ThresholdRule
	err := s.store.View(func(tx *bbolt.Tx) error {
		raw := tx.Bucket(thresholdsBucket).Get([]byte(req.GetRuleId()))
		if raw == nil {
			return status.Errorf(codes.NotFound, "rule_id %q not found", req.GetRuleId())
		}
		rule = &sidecarsv1.ThresholdRule{}
		return json.Unmarshal(raw, rule)
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "load: %v", err)
	}
	window, _ := time.ParseDuration(rule.GetWindow())
	since := time.Now().Add(-window).UnixNano()
	matched := 0
	s.mu.RLock()
	for _, b := range s.recent {
		if b.GetEventType() != rule.GetEventType() {
			continue
		}
		if b.GetPostedAtUnixNanos() < since {
			break
		}
		matched++
	}
	s.mu.RUnlock()
	return &sidecarsv1.EvaluationReport{
		RuleId:       rule.GetId(),
		WouldFire:    int32(matched) >= rule.GetCount(),
		MatchedCount: int32(matched),
		Detail:       "evaluated against in-memory recent feed",
	}, nil
}

// PromoteToAutoIssue is the boundary call: the Channels bridge invokes this
// after detecting a threshold fire, and bullboard ACKS. The actual AutoIssue
// creation happens in apps.auto_issues.api.file_autoissue (Python side).
// bullboard intentionally does NOT call governance directly to keep the
// cross-module boundary in Python.
func (s *Server) PromoteToAutoIssue(_ context.Context, req *sidecarsv1.PromoteRequest) (*sidecarsv1.Ack, error) {
	if req.GetEventType() == "" {
		return nil, status.Error(codes.InvalidArgument, "event_type is required")
	}
	s.logger.Info("promote requested",
		"rule_id", req.GetRuleId(), "event_type", req.GetEventType())
	return &sidecarsv1.Ack{Ok: true, Detail: "logged; caller files the AutoIssue"}, nil
}

func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

func (s *Server) warmRecentFromDisk() {
	bulletins := make([]*sidecarsv1.Bulletin, 0, maxRecentInMemory)
	_ = s.store.View(func(tx *bbolt.Tx) error {
		c := tx.Bucket(bulletinsBucket).Cursor()
		// Iterate from newest (last key) backwards.
		for k, v := c.Last(); k != nil && len(bulletins) < maxRecentInMemory; k, v = c.Prev() {
			b := &sidecarsv1.Bulletin{}
			if err := json.Unmarshal(v, b); err != nil {
				continue
			}
			bulletins = append(bulletins, b)
		}
		return nil
	})
	sort.Slice(bulletins, func(i, j int) bool {
		return bulletins[i].GetPostedAtUnixNanos() > bulletins[j].GetPostedAtUnixNanos()
	})
	s.mu.Lock()
	s.recent = bulletins
	s.mu.Unlock()
}

// bulletinKey produces a sortable key combining nanoseconds and id.
func bulletinKey(at time.Time, id string) []byte {
	ns := at.UnixNano()
	return []byte(time.Unix(0, ns).Format("20060102T150405.000000000") + ":" + id)
}

var _ idle.Idler = (*Server)(nil)
