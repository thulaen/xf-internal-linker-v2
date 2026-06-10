// Package coordd is the Zookeeper-style coordination service.
//
// Slice 1.6 implements the unary RPCs (CreateEphemeral, Lock, Unlock,
// Discover) plus Health. The streaming RPCs (Watch, Elect) inherit
// codes.Unimplemented from UnimplementedCoorddServer this slice — they
// fill in via a follow-up tracked in the paper-trail under
// `sidecars_followup`.
package coordd

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"
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
	ServiceName         = "coordd"
	defaultEphemeralTTL = 30 * time.Second
	defaultLockHold     = 10 * time.Second
)

var (
	nodesBucket = []byte("nodes")
	locksBucket = []byte("locks")
)

type Server struct {
	sidecarsv1.UnimplementedCoorddServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time

	mu        sync.Mutex
	heldLocks map[string]string // lock_name -> token

	// Watch + Elect streaming fan-out (slice 1.6 streaming RPCs).
	watchersMu sync.Mutex
	watchers   map[string]*watcher // keyed by subscription uuid
	electorsMu sync.Mutex
	electors   map[string]*elector // keyed by subscription uuid
	leadersMu  sync.Mutex
	leaders    map[string]string // group -> leader_id (current leader cache)
}

type watcher struct {
	ch        chan *sidecarsv1.WatchEvent
	path      string
	recursive bool
}

type elector struct {
	ch          chan *sidecarsv1.LeaderEvent
	group       string
	candidateID string
}

const watcherBuffer = 32
const electorBuffer = 8

type lockRecord struct {
	Token     string    `json:"token"`
	LockName  string    `json:"lock_name"`
	ExpiresAt time.Time `json:"expires_at"`
}

type nodeRecord struct {
	ID        string    `json:"id"`
	Path      string    `json:"path"`
	Data      []byte    `json:"data"`
	ExpiresAt time.Time `json:"expires_at"`
}

func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{
		store:     db,
		logger:    logger.With("service", ServiceName),
		startedAt: time.Now(),
		heldLocks: make(map[string]string),
		watchers:  make(map[string]*watcher),
		electors:  make(map[string]*elector),
		leaders:   make(map[string]string),
	}
	_ = s.store.Update(func(tx *bbolt.Tx) error {
		for _, b := range [][]byte{nodesBucket, locksBucket} {
			if _, err := tx.CreateBucketIfNotExists(b); err != nil {
				return err
			}
		}
		return nil
	})
	sidecarsv1.RegisterCoorddServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityHigh)
	return s
}

func (s *Server) Idle() {
	s.mu.Lock()
	s.heldLocks = make(map[string]string)
	s.mu.Unlock()
}

func (s *Server) CreateEphemeral(_ context.Context, req *sidecarsv1.EphemeralRequest) (*sidecarsv1.NodeID, error) {
	if req.GetPath() == "" {
		return nil, status.Error(codes.InvalidArgument, "path is required")
	}
	ttl := defaultEphemeralTTL
	if req.GetTtlSeconds() > 0 {
		ttl = time.Duration(req.GetTtlSeconds()) * time.Second
	}
	now := time.Now()
	node := nodeRecord{
		ID:        uuid.New().String(),
		Path:      req.GetPath(),
		Data:      req.GetData(),
		ExpiresAt: now.Add(ttl),
	}
	raw, err := json.Marshal(node)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(nodesBucket).Put([]byte(node.ID), raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	s.fanOutWatchEvent(&sidecarsv1.WatchEvent{
		Kind: sidecarsv1.WatchKind_WATCH_CREATED,
		Path: node.Path,
		Data: node.Data,
	})
	return &sidecarsv1.NodeID{
		Id:                 node.ID,
		Path:               node.Path,
		CreatedAtUnixNanos: now.UnixNano(),
	}, nil
}

func (s *Server) Lock(_ context.Context, req *sidecarsv1.LockRequest) (*sidecarsv1.LockToken, error) {
	if req.GetLockName() == "" {
		return nil, status.Error(codes.InvalidArgument, "lock_name is required")
	}
	hold := defaultLockHold
	if req.GetHoldForSeconds() > 0 {
		hold = time.Duration(req.GetHoldForSeconds()) * time.Second
	}
	now := time.Now()
	expiresAt := now.Add(hold)
	token := uuid.New().String()

	s.mu.Lock()
	defer s.mu.Unlock()
	// Check whether the lock is currently held (token exists and not expired).
	if held, ok := s.heldLocks[req.GetLockName()]; ok {
		var rec lockRecord
		err := s.store.View(func(tx *bbolt.Tx) error {
			raw := tx.Bucket(locksBucket).Get([]byte(held))
			if raw == nil {
				return nil
			}
			return json.Unmarshal(raw, &rec)
		})
		if err == nil && rec.ExpiresAt.After(now) {
			return nil, status.Errorf(codes.FailedPrecondition, "lock %q already held until %s",
				req.GetLockName(), rec.ExpiresAt.Format(time.RFC3339))
		}
		// expired — fall through and take over
		delete(s.heldLocks, req.GetLockName())
	}

	rec := lockRecord{Token: token, LockName: req.GetLockName(), ExpiresAt: expiresAt}
	raw, err := json.Marshal(rec)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "marshal: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(locksBucket).Put([]byte(token), raw)
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "put: %v", err)
	}
	s.heldLocks[req.GetLockName()] = token
	return &sidecarsv1.LockToken{
		Token:              token,
		LockName:           req.GetLockName(),
		ExpiresAtUnixNanos: expiresAt.UnixNano(),
	}, nil
}

func (s *Server) Unlock(_ context.Context, req *sidecarsv1.UnlockRequest) (*sidecarsv1.Ack, error) {
	if req.GetToken() == "" {
		return nil, status.Error(codes.InvalidArgument, "token is required")
	}
	var rec lockRecord
	err := s.store.View(func(tx *bbolt.Tx) error {
		raw := tx.Bucket(locksBucket).Get([]byte(req.GetToken()))
		if raw == nil {
			return status.Error(codes.NotFound, "token not found")
		}
		return json.Unmarshal(raw, &rec)
	})
	if err != nil {
		if _, ok := status.FromError(err); ok {
			return nil, err
		}
		return nil, status.Errorf(codes.Internal, "lookup: %v", err)
	}
	err = s.store.Update(func(tx *bbolt.Tx) error {
		return tx.Bucket(locksBucket).Delete([]byte(req.GetToken()))
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "delete: %v", err)
	}
	s.mu.Lock()
	delete(s.heldLocks, rec.LockName)
	s.mu.Unlock()
	return &sidecarsv1.Ack{Ok: true, Detail: "released lock " + rec.LockName}, nil
}

func (s *Server) Discover(_ context.Context, req *sidecarsv1.DiscoverRequest) (*sidecarsv1.ServiceList, error) {
	if req.GetGroup() == "" {
		return nil, status.Error(codes.InvalidArgument, "group is required")
	}
	now := time.Now()
	members := make([]string, 0, 8)
	err := s.store.View(func(tx *bbolt.Tx) error {
		return tx.Bucket(nodesBucket).ForEach(func(_, v []byte) error {
			var n nodeRecord
			if err := json.Unmarshal(v, &n); err != nil {
				return nil
			}
			if !strings.HasPrefix(n.Path, "/"+req.GetGroup()+"/") {
				return nil
			}
			if n.ExpiresAt.Before(now) {
				return nil // expired ephemeral; treat as gone
			}
			members = append(members, n.ID)
			return nil
		})
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "discover: %v", err)
	}
	return &sidecarsv1.ServiceList{Members: members}, nil
}

func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}

// Watch is the slice-1.6 streaming Watch RPC. Registers a watcher with a
// 32-buffer channel and streams every WatchEvent whose path matches the
// filter (exact path, or any descendant when recursive=true) until the
// caller's context is cancelled. CreateEphemeral fan-outs into watchers
// at write time so live observers see node creation events.
func (s *Server) Watch(req *sidecarsv1.WatchRequest, stream sidecarsv1.Coordd_WatchServer) error {
	if req.GetPath() == "" {
		return status.Error(codes.InvalidArgument, "path is required")
	}
	w := &watcher{
		ch:        make(chan *sidecarsv1.WatchEvent, watcherBuffer),
		path:      req.GetPath(),
		recursive: req.GetRecursive(),
	}
	id := uuid.New().String()
	s.watchersMu.Lock()
	s.watchers[id] = w
	s.watchersMu.Unlock()
	s.logger.Info("watcher attached", "watcher_id", id, "path", w.path, "recursive", w.recursive)
	defer func() {
		s.watchersMu.Lock()
		delete(s.watchers, id)
		s.watchersMu.Unlock()
		s.logger.Info("watcher detached", "watcher_id", id)
	}()
	ctx := stream.Context()
	for {
		select {
		case <-ctx.Done():
			return nil
		case ev := <-w.ch:
			if err := stream.Send(ev); err != nil {
				return err
			}
		}
	}
}

// Elect is the slice-1.6 streaming leader-election RPC. Each candidate
// opens a stream; the first candidate per group becomes leader, the rest
// remain followers and receive LeaderEvents when the leader changes
// (today: only on initial join; future paper-trail entry covers proper
// session-token-backed re-election on disconnect).
func (s *Server) Elect(req *sidecarsv1.ElectRequest, stream sidecarsv1.Coordd_ElectServer) error {
	if req.GetGroup() == "" {
		return status.Error(codes.InvalidArgument, "group is required")
	}
	if req.GetCandidateId() == "" {
		return status.Error(codes.InvalidArgument, "candidate_id is required")
	}
	e := &elector{
		ch:          make(chan *sidecarsv1.LeaderEvent, electorBuffer),
		group:       req.GetGroup(),
		candidateID: req.GetCandidateId(),
	}
	id := uuid.New().String()

	// Take leadership if no one else holds it for this group; otherwise
	// register as a follower.
	s.leadersMu.Lock()
	currentLeader, hasLeader := s.leaders[req.GetGroup()]
	becameLeader := false
	if !hasLeader {
		s.leaders[req.GetGroup()] = req.GetCandidateId()
		becameLeader = true
		currentLeader = req.GetCandidateId()
	}
	s.leadersMu.Unlock()

	s.electorsMu.Lock()
	s.electors[id] = e
	s.electorsMu.Unlock()
	defer func() {
		s.electorsMu.Lock()
		delete(s.electors, id)
		s.electorsMu.Unlock()
		// If the leader just left, hand over leadership to the longest-
		// waiting follower (any follower will do; ordering is best-effort).
		s.leadersMu.Lock()
		if cur, ok := s.leaders[req.GetGroup()]; ok && cur == req.GetCandidateId() {
			delete(s.leaders, req.GetGroup())
			s.electorsMu.Lock()
			for _, other := range s.electors {
				if other.group == req.GetGroup() {
					s.leaders[req.GetGroup()] = other.candidateID
					select {
					case other.ch <- &sidecarsv1.LeaderEvent{
						Kind:     sidecarsv1.LeaderKind_LEAD_BECAME,
						Group:    req.GetGroup(),
						LeaderId: other.candidateID,
					}:
					default:
					}
					break
				}
			}
			s.electorsMu.Unlock()
		}
		s.leadersMu.Unlock()
		s.logger.Info("elector detached", "elector_id", id, "candidate", req.GetCandidateId())
	}()

	// Emit the initial event (BECAME_LEADER if we won, LEADER_CHANGED if
	// someone else is already leading).
	var initialKind sidecarsv1.LeaderKind
	if becameLeader {
		initialKind = sidecarsv1.LeaderKind_LEAD_BECAME
	} else {
		initialKind = sidecarsv1.LeaderKind_LEAD_CHANGED
	}
	if err := stream.Send(&sidecarsv1.LeaderEvent{
		Kind:     initialKind,
		Group:    req.GetGroup(),
		LeaderId: currentLeader,
	}); err != nil {
		return err
	}

	ctx := stream.Context()
	for {
		select {
		case <-ctx.Done():
			return nil
		case ev := <-e.ch:
			if err := stream.Send(ev); err != nil {
				return err
			}
		}
	}
}

// fanOutWatchEvent is called after a successful node mutation. It pushes
// the event to every watcher whose path matches.
func (s *Server) fanOutWatchEvent(ev *sidecarsv1.WatchEvent) {
	s.watchersMu.Lock()
	defer s.watchersMu.Unlock()
	for id, w := range s.watchers {
		if !pathMatches(w.path, ev.GetPath(), w.recursive) {
			continue
		}
		select {
		case w.ch <- ev:
		default:
			s.logger.Debug("watcher dropped event (buffer full)",
				"watcher_id", id, "path", ev.GetPath())
		}
	}
}

func pathMatches(filter, observed string, recursive bool) bool {
	if filter == observed {
		return true
	}
	if !recursive {
		return false
	}
	// recursive: observed is a strict descendant of filter.
	return len(observed) > len(filter) && observed[:len(filter)] == filter &&
		(observed[len(filter)] == '/' || filter == "/")
}

var _ idle.Idler = (*Server)(nil)
