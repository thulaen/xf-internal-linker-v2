// Package attrouted is the NiFi-style route-on-attribute work router.
//
// Slice 1.6: rules live in memory + are persisted to Bolt; the audit trail
// (per-unit-id decision history) lives in a separate bucket so Replay can
// reconstruct what the rule set decided at the time vs what it would decide
// now.
package attrouted

import (
	"context"
	"encoding/json"
	"log/slog"
	"sort"
	"sync"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

const ServiceName = "attrouted"

var (
	rulesBucket = []byte("rules")
	auditBucket = []byte("audit")
)

type Server struct {
	sidecarsv1.UnimplementedAttroutedServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time

	mu    sync.RWMutex
	rules map[string]*sidecarsv1.RouteRule // cached for fast routing
}

func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{
		store:     db,
		logger:    logger.With("service", ServiceName),
		startedAt: time.Now(),
		rules:     make(map[string]*sidecarsv1.RouteRule),
	}
	_ = s.store.Update(func(tx *bbolt.Tx) error {
		for _, b := range [][]byte{rulesBucket, auditBucket} {
			if _, err := tx.CreateBucketIfNotExists(b); err != nil {
				return err
			}
		}
		return nil
	})
	s.loadRulesFromDisk()
	sidecarsv1.RegisterAttroutedServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

// Idle clears the in-memory rule cache; the disk copy is the source of truth.
// Next Route() refills the cache.
func (s *Server) Idle() {
	s.mu.Lock()
	s.rules = make(map[string]*sidecarsv1.RouteRule)
	s.mu.Unlock()
}

func (s *Server) loadRulesFromDisk() {
	cache := make(map[string]*sidecarsv1.RouteRule)
	_ = s.store.View(func(tx *bbolt.Tx) error {
		return tx.Bucket(rulesBucket).ForEach(func(_, v []byte) error {
			r := &sidecarsv1.RouteRule{}
			if err := json.Unmarshal(v, r); err != nil {
				return nil
			}
			cache[r.GetId()] = r
			return nil
		})
	})
	s.mu.Lock()
	s.rules = cache
	s.mu.Unlock()
}

func (s *Server) Route(_ context.Context, req *sidecarsv1.RouteRequest) (*sidecarsv1.RouteDecision, error) {
	if req.GetSource() == "" {
		return nil, status.Error(codes.InvalidArgument, "source is required")
	}
	s.mu.RLock()
	if len(s.rules) == 0 {
		s.mu.RUnlock()
		s.loadRulesFromDisk()
		s.mu.RLock()
	}
	rules := make([]*sidecarsv1.RouteRule, 0, len(s.rules))
	for _, r := range s.rules {
		if r.GetSource() == req.GetSource() && r.GetEnabled() {
			rules = append(rules, r)
		}
	}
	s.mu.RUnlock()
	sort.Slice(rules, func(i, j int) bool { return rules[i].Priority > rules[j].Priority })

	for _, r := range rules {
		if attributesMatch(r.GetMatchAttributes(), req.GetAttributes()) {
			dec := &sidecarsv1.RouteDecision{
				MatchedRuleId: r.GetId(),
				Target:        r.GetTarget(),
				Explanation:   "matched rule id=" + r.GetId() + " → " + r.GetTarget(),
			}
			s.maybeRecordAudit(req, dec)
			return dec, nil
		}
	}
	dec := &sidecarsv1.RouteDecision{
		Target:      "default",
		Explanation: "no rule matched; defaulted to 'default' target",
	}
	s.maybeRecordAudit(req, dec)
	return dec, nil
}

func (s *Server) RegisterRule(_ context.Context, r *sidecarsv1.RouteRule) (*sidecarsv1.RouteRule, error) {
	if r.GetSource() == "" {
		return nil, status.Error(codes.InvalidArgument, "source is required")
	}
	if r.GetTarget() == "" {
		return nil, status.Error(codes.InvalidArgument, "target is required")
	}
	if r.GetId() == "" {
		r.Id = "r:" + r.GetSource() + ":" + time.Now().Format("20060102150405.000000")
	}
	raw, err := json.Marshal(r)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(rulesBucket).Put([]byte(r.GetId()), raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	s.mu.Lock()
	s.rules[r.GetId()] = r
	s.mu.Unlock()
	return r, nil
}

func (s *Server) ListRules(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.RouteRuleList, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := &sidecarsv1.RouteRuleList{}
	for _, r := range s.rules {
		out.Items = append(out.Items, r)
	}
	return out, nil
}

func (s *Server) RemoveRule(_ context.Context, req *sidecarsv1.RemoveRuleRequest) (*sidecarsv1.Ack, error) {
	if req.GetRuleId() == "" {
		return nil, status.Error(codes.InvalidArgument, "rule_id is required")
	}
	err := s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(rulesBucket).Delete([]byte(req.GetRuleId()))
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "delete: %v", err)
	}
	s.mu.Lock()
	delete(s.rules, req.GetRuleId())
	s.mu.Unlock()
	return &sidecarsv1.Ack{Ok: true, Detail: "rule removed"}, nil
}

func (s *Server) Replay(_ context.Context, req *sidecarsv1.ReplayRequest) (*sidecarsv1.ReplayReport, error) {
	if req.GetUnitId() == "" {
		return nil, status.Error(codes.InvalidArgument, "unit_id is required")
	}
	var rec auditRecord
	err := s.store.View(func(tx *bbolt.Tx) error {
		raw := tx.Bucket(auditBucket).Get([]byte(req.GetUnitId()))
		if raw == nil {
			return status.Errorf(codes.NotFound, "unit_id %q not in audit log", req.GetUnitId())
		}
		return json.Unmarshal(raw, &rec)
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "replay: %v", err)
	}
	now, _ := s.Route(context.Background(), rec.Request)
	report := &sidecarsv1.ReplayReport{
		UnitId:       req.GetUnitId(),
		ThenDecision: rec.Decision,
		NowDecision:  now,
	}
	if rec.Decision.GetTarget() == now.GetTarget() {
		report.DiffExplanation = "no change"
	} else {
		report.DiffExplanation = "target moved from " + rec.Decision.GetTarget() + " to " + now.GetTarget()
	}
	return report, nil
}

func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

type auditRecord struct {
	Request  *sidecarsv1.RouteRequest  `json:"request"`
	Decision *sidecarsv1.RouteDecision `json:"decision"`
	At       time.Time                 `json:"at"`
}

func (s *Server) maybeRecordAudit(req *sidecarsv1.RouteRequest, dec *sidecarsv1.RouteDecision) {
	if req.GetUnitId() == "" {
		return
	}
	rec := auditRecord{Request: req, Decision: dec, At: time.Now()}
	raw, err := json.Marshal(rec)
	if err != nil {
		s.logger.Warn("audit marshal failed", "err", err)
		return
	}
	if err := s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(auditBucket).Put([]byte(req.GetUnitId()), raw)
	}); err != nil {
		s.logger.Warn("audit put failed", "err", err)
	}
}

func attributesMatch(rule, got map[string]string) bool {
	for key, want := range rule {
		if want == "" { // "" → any
			if _, ok := got[key]; !ok {
				return false
			}
			continue
		}
		if got[key] != want {
			return false
		}
	}
	return true
}

var _ idle.Idler = (*Server)(nil)
