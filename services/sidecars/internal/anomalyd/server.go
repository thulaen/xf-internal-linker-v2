// Package anomalyd is the gRPC skeleton for the anomalyd sidecar service.
// Apache reference: Eagle. Owning Django module: operations.
//
// Slice 1.6 ships this service as a skeleton: every RPC returns
// codes.Unimplemented. The full implementation lands in a future slice;
// paper-trail entry tagged `sidecars_followup` tracks the work.
package anomalyd

import (
	"context"
	"log/slog"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc"

	sidecarsv1 "xf-internal-linker-v2/services/sidecars/api/gen"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
)

// ServiceName is the canonical name used in the manifest, idle tracker, and logs.
const ServiceName = "anomalyd"

// Server is the gRPC handler for anomalyd.
type Server struct {
	sidecarsv1.UnimplementedAnomalydServer
	store     *bbolt.DB
	logger    *slog.Logger
	startedAt time.Time
}

// Register wires the server onto the shared gRPC server + idle tracker.
func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {
	s := &Server{store: db, logger: logger.With("service", ServiceName), startedAt: time.Now()}
	sidecarsv1.RegisterAnomalydServer(grpcSrv, s)
	tracker.Register(ServiceName, s, idle.PriorityMedium)
	return s
}

// Idle releases caches under memory pressure. Skeleton: no-op.
func (s *Server) Idle() {}

// Health returns HEALTH_SERVING. Skeletons answer Health so the
// sidecars-healthcheck binary can verify the gRPC server is up before any
// individual service is fully implemented.
func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {
	return &sidecarsv1.HealthReply{
		Status:    sidecarsv1.HealthStatus_HEALTH_SERVING,
		StartedAt: s.startedAt.UTC().Format(time.RFC3339),
		Service:   ServiceName,
	}, nil
}
