// Package errord is the Camel-style exception-policy registry.
//
// Slice 1.6: the operations module calls Handle(...) when an exception
// bubbles up. errord matches against the registered policies (highest
// priority first) and returns the action to take. errord does not file
// AutoIssues itself — the caller owns that boundary.
package errord

import (
	"context"
	"encoding/json"
	"log/slog"
	"sort"
	"strings"
	"sync/atomic"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

const ServiceName = "errord"

var policiesBucket = []byte("policies")

type Server struct {
	sidecarsv1.UnimplementedErrordServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time

	handled, swallowed, retried, alerted, autoissues atomic.Int64
}

func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{store: db, logger: logger.With("service", ServiceName), startedAt: time.Now()}
	_ = s.store.Update(func(tx *bbolt.Tx) error {
		_, err := tx.CreateBucketIfNotExists(policiesBucket)
		return err
	})
	sidecarsv1.RegisterErrordServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

func (s *Server) Idle() {}

func (s *Server) RegisterPolicy(_ context.Context, p *sidecarsv1.ErrorPolicy) (*sidecarsv1.ErrorPolicy, error) {
	if p.GetMatchClass() == "" {
		return nil, status.Error(codes.InvalidArgument, "match_class is required")
	}
	if p.GetAction() == sidecarsv1.HandleAction_ACT_UNKNOWN {
		return nil, status.Error(codes.InvalidArgument, "action is required")
	}
	if p.GetId() == "" {
		p.Id = generateID(p.GetMatchClass(), p.GetMatchModule())
	}
	raw, err := json.Marshal(p)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(policiesBucket).Put([]byte(p.GetId()), raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	return p, nil
}

func (s *Server) Handle(_ context.Context, req *sidecarsv1.HandleExceptionRequest) (*sidecarsv1.HandleResult, error) {
	s.handled.Add(1)
	policies, err := s.loadAll()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "load_policies: %v", err)
	}
	sort.Slice(policies, func(i, j int) bool { return policies[i].Priority > policies[j].Priority })
	for _, p := range policies {
		if !p.GetEnabled() {
			continue
		}
		if !matches(p, req) {
			continue
		}
		switch p.GetAction() {
		case sidecarsv1.HandleAction_ACT_SWALLOW:
			s.swallowed.Add(1)
		case sidecarsv1.HandleAction_ACT_RETRY:
			s.retried.Add(1)
		case sidecarsv1.HandleAction_ACT_ALERT:
			s.alerted.Add(1)
		case sidecarsv1.HandleAction_ACT_FILE_AUTOISSUE:
			s.autoissues.Add(1)
		}
		return &sidecarsv1.HandleResult{
			MatchedPolicyId:   p.GetId(),
			Action:            p.GetAction(),
			BackoffSeconds:    p.GetBackoffSeconds(),
			Explanation:       explain(p, req),
			AutoissueSeverity: p.GetAutoissueSeverity(),
		}, nil
	}
	// Default: ALERT so something visible happens.
	s.alerted.Add(1)
	return &sidecarsv1.HandleResult{
		Action:      sidecarsv1.HandleAction_ACT_ALERT,
		Explanation: "no matching policy; defaulting to ALERT",
	}, nil
}

func (s *Server) ListPolicies(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.ErrorPolicyList, error) {
	policies, err := s.loadAll()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "list: %v", err)
	}
	return &sidecarsv1.ErrorPolicyList{Items: policies}, nil
}

func (s *Server) Stats(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.ErrorStats, error) {
	return &sidecarsv1.ErrorStats{
		TotalHandled:        s.handled.Load(),
		TotalSwallowed:      s.swallowed.Load(),
		TotalRetried:        s.retried.Load(),
		TotalAlerted:        s.alerted.Load(),
		TotalAutoissueFiled: s.autoissues.Load(),
	}, nil
}

func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

func (s *Server) loadAll() ([]*sidecarsv1.ErrorPolicy, error) {
	var out []*sidecarsv1.ErrorPolicy
	err := s.store.View(func(tx *bbolt.Tx) error {
		return tx.Bucket(policiesBucket).ForEach(func(_, v []byte) error {
			p := &sidecarsv1.ErrorPolicy{}
			if err := json.Unmarshal(v, p); err != nil {
				return err
			}
			out = append(out, p)
			return nil
		})
	})
	return out, err
}

func matches(p *sidecarsv1.ErrorPolicy, req *sidecarsv1.HandleExceptionRequest) bool {
	if p.GetMatchClass() != "" && !strings.Contains(req.GetClassName(), p.GetMatchClass()) {
		return false
	}
	if p.GetMatchModule() != "" && !strings.HasPrefix(req.GetModule(), p.GetMatchModule()) {
		return false
	}
	return true
}

func explain(p *sidecarsv1.ErrorPolicy, req *sidecarsv1.HandleExceptionRequest) string {
	parts := []string{"matched policy id=" + p.GetId()}
	if p.GetMatchClass() != "" {
		parts = append(parts, "class~"+p.GetMatchClass())
	}
	if p.GetMatchModule() != "" {
		parts = append(parts, "module="+p.GetMatchModule())
	}
	parts = append(parts, "→ "+p.GetAction().String())
	_ = req
	return strings.Join(parts, " ")
}

func generateID(class, module string) string {
	return "p:" + strings.ReplaceAll(class+":"+module+":"+time.Now().Format("20060102150405.000000"), "/", "_")
}

var _ idle.Idler = (*Server)(nil)
