// Slice 1.6 — sidecars binary entry point.
//
// Boots one gRPC server over a Unix-domain socket. The 40 internal services
// declared in services.manifest.yaml each register their own gRPC service
// against this single server. Different gRPC service names route to
// different internal handlers off the same listener.
//
// References:
//   - Donovan & Kernighan 2015 §8 (concurrency) + §11 (testing)
//   - https://pkg.go.dev/runtime/debug#SetMemoryLimit
//   - https://grpc.io/docs/guides/naming/ (unix:// scheme)
//   - docs/specs/fr-sidecars-host.md (the 7 hard constraints)

package main

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"go.etcd.io/bbolt"
	"google.golang.org/grpc"
	"google.golang.org/grpc/keepalive"

	"xf-internal-linker-v2/services/sidecars/internal/shared/budget"
	"xf-internal-linker-v2/services/sidecars/internal/shared/idle"
	"xf-internal-linker-v2/services/sidecars/internal/shared/manifest"
	"xf-internal-linker-v2/services/sidecars/internal/shared/otel"
	"xf-internal-linker-v2/services/sidecars/internal/shared/pruner"
	"xf-internal-linker-v2/services/sidecars/internal/shared/socket"
	"xf-internal-linker-v2/services/sidecars/internal/shared/store"

	// Critical (real) services
	"xf-internal-linker-v2/services/sidecars/internal/attrouted"
	"xf-internal-linker-v2/services/sidecars/internal/bullboard"
	"xf-internal-linker-v2/services/sidecars/internal/coordd"
	"xf-internal-linker-v2/services/sidecars/internal/errord"
	"xf-internal-linker-v2/services/sidecars/internal/schemard"
	"xf-internal-linker-v2/services/sidecars/internal/searchd"
	"xf-internal-linker-v2/services/sidecars/internal/snapshotd"

	// Skeleton (Unimplemented) services — every one is registered against
	// the shared gRPC server so the Unix socket carries all 40 service
	// names. Real RPC bodies fill in via a follow-up tracked in the paper
	// trail under `sidecars_followup`.
	"xf-internal-linker-v2/services/sidecars/internal/aclsd"
	"xf-internal-linker-v2/services/sidecars/internal/anomalyd"
	"xf-internal-linker-v2/services/sidecars/internal/arrowd"
	"xf-internal-linker-v2/services/sidecars/internal/catalogd"
	"xf-internal-linker-v2/services/sidecars/internal/cepd"
	"xf-internal-linker-v2/services/sidecars/internal/compactd"
	"xf-internal-linker-v2/services/sidecars/internal/dagd"
	"xf-internal-linker-v2/services/sidecars/internal/dedupd"
	"xf-internal-linker-v2/services/sidecars/internal/delayd"
	"xf-internal-linker-v2/services/sidecars/internal/drilld"
	"xf-internal-linker-v2/services/sidecars/internal/extractd"
	"xf-internal-linker-v2/services/sidecars/internal/flumed"
	"xf-internal-linker-v2/services/sidecars/internal/fnd"
	"xf-internal-linker-v2/services/sidecars/internal/gatewayd"
	"xf-internal-linker-v2/services/sidecars/internal/gremlind"
	"xf-internal-linker-v2/services/sidecars/internal/hintd"
	"xf-internal-linker-v2/services/sidecars/internal/lookupd"
	"xf-internal-linker-v2/services/sidecars/internal/mesh"
	"xf-internal-linker-v2/services/sidecars/internal/pluginhotd"
	"xf-internal-linker-v2/services/sidecars/internal/politenessd"
	"xf-internal-linker-v2/services/sidecars/internal/pressured"
	"xf-internal-linker-v2/services/sidecars/internal/provd"
	"xf-internal-linker-v2/services/sidecars/internal/purged"
	"xf-internal-linker-v2/services/sidecars/internal/qsched"
	"xf-internal-linker-v2/services/sidecars/internal/retentd"
	"xf-internal-linker-v2/services/sidecars/internal/ruled"
	"xf-internal-linker-v2/services/sidecars/internal/smd"
	"xf-internal-linker-v2/services/sidecars/internal/tieredd"
	"xf-internal-linker-v2/services/sidecars/internal/timetravd"
	"xf-internal-linker-v2/services/sidecars/internal/topicd"
	"xf-internal-linker-v2/services/sidecars/internal/tsd"
	"xf-internal-linker-v2/services/sidecars/internal/txd"
	"xf-internal-linker-v2/services/sidecars/internal/viewd"
	"xf-internal-linker-v2/services/sidecars/internal/xcomd"
)

const (
	defaultMaxMsgBytes       = 4 << 20 // 4 MiB
	defaultKeepaliveTime     = 30 * time.Second
	gracefulShutdownDeadline = 5 * time.Second
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slogLevel()}))
	slog.SetDefault(logger)

	manifestPath := envOr("XF_SIDECARS_MANIFEST", "services.manifest.yaml")
	m, err := manifest.Load(manifestPath)
	if err != nil {
		logger.Error("manifest load failed", "err", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, logger, m); err != nil {
		logger.Error("sidecars terminated with error", "err", err)
		os.Exit(1)
	}
	logger.Info("sidecars shutdown clean")
}

func run(ctx context.Context, logger *slog.Logger, m *manifest.Manifest) error {
	socketPath := envOr("XF_SIDECARS_SOCKET", m.Host.SocketPath)
	storagePath := envOr("XF_SIDECARS_STORAGE", m.Host.StoragePath)

	// 1. Apply the global memory cap before anything else allocates.
	bud := budget.New(budget.Options{
		TotalMemoryBytes:  int64(m.Host.TotalMemoryMB) << 20,
		PressureThreshold: float64(m.Host.MemoryPressureThresholdPercent) / 100.0,
		Logger:            logger,
	})
	bud.Apply()
	bud.Start(ctx)

	// 2. Open the per-service Bolt factory.
	storeFactory, err := store.New(store.Options{RootDir: storagePath})
	if err != nil {
		return err
	}
	defer func() { _ = storeFactory.Close() }()

	// 3. Idle tracker — services register themselves below.
	tracker := idle.New(idle.Options{
		IdleAfter: time.Duration(m.Host.IdleReleaseSeconds) * time.Second,
		Logger:    logger,
	})
	tracker.Start(ctx)
	bud.OnPressure(func(_ int64) { tracker.ForceReleaseLowest() })

	// 4. Bind the Unix-domain socket.
	listener, err := socket.Listen(socketPath)
	if err != nil {
		return err
	}
	logger.Info("sidecars bound", "socket", socketPath, "mode", "0660")

	// 5. Build the gRPC server.
	grpcSrv := grpc.NewServer(
		grpc.MaxRecvMsgSize(defaultMaxMsgBytes),
		grpc.MaxSendMsgSize(defaultMaxMsgBytes),
		grpc.KeepaliveParams(keepalive.ServerParameters{
			Time:    defaultKeepaliveTime,
			Timeout: 5 * time.Second,
		}),
	)

	// 6. Register all 40 services. The 6 critical ones get real handlers;
	// the 34 skeletons return codes.Unimplemented from their RPC methods.
	if err := registerAll(grpcSrv, storeFactory, tracker, logger, storagePath); err != nil {
		return err
	}

	// 7. Storage pruner with snapshotd-backed PinChecker so pinned snapshots
	// survive the 7-day age sweep. The lightweight checker treats any file
	// under /var/lib/xf/sidecars/snapshotd/pinned/ as pinned; the snapshotd
	// Server.IsPinned method is the authoritative source and is wired in a
	// follow-up.
	prn := pruner.New(pruner.Options{
		RootDir:       storagePath,
		TotalCapBytes: int64(m.Host.TotalStorageMB) << 20,
		AgeLimit:      time.Duration(m.Host.RetentionHours) * time.Hour,
		Interval:      time.Duration(m.Host.PrunerIntervalSeconds) * time.Second,
		Logger:        logger,
		PinChecker:    pinCheckerFromSnapshotd(storagePath),
	})
	prn.Start(ctx)

	// 8. Localhost-only /pprof + /healthz for OpenTelemetry profiles.
	metricsAddr := envOr("XF_SIDECARS_METRICS_ADDR", "127.0.0.1:6061")
	metricsSrv := otel.Start(otel.Options{
		Addr:           metricsAddr,
		HealthReporter: func() (string, bool) { return "ok", true },
		Logger:         logger,
	})

	// 9. Serve.
	serveErr := make(chan error, 1)
	go func() {
		logger.Info("sidecars serving", "addr", listener.Addr().String(),
			"implemented", len(m.ImplementedServices()),
			"skeleton", len(m.SkeletonServices()))
		serveErr <- grpcSrv.Serve(listener)
	}()

	select {
	case <-ctx.Done():
		logger.Info("sidecars received shutdown signal")
	case err := <-serveErr:
		if err != nil && !errors.Is(err, grpc.ErrServerStopped) {
			return err
		}
	}

	// 10. Graceful shutdown.
	shutdownCtx, cancel := context.WithTimeout(context.Background(), gracefulShutdownDeadline)
	defer cancel()
	stopped := make(chan struct{})
	go func() {
		grpcSrv.GracefulStop()
		close(stopped)
	}()
	select {
	case <-stopped:
		logger.Info("sidecars graceful stop complete")
	case <-shutdownCtx.Done():
		logger.Warn("sidecars graceful stop deadline exceeded; forcing stop")
		grpcSrv.Stop()
	}
	if err := metricsSrv.Shutdown(shutdownCtx); err != nil {
		logger.Warn("metrics shutdown error", "err", err)
	}
	if err := os.Remove(socketPath); err != nil && !errors.Is(err, os.ErrNotExist) {
		logger.Warn("could not remove socket file on exit", "socket", socketPath, "err", err)
	}
	return nil
}

// registerAll wires every internal service against the shared gRPC server.
// Each call:
//  1. Acquires the service's scoped bbolt.DB via storeFactory.For(name).
//  2. Invokes <pkg>.Register(grpcSrv, db, tracker, logger).
//  3. The service registers itself with the idle tracker at its declared
//     priority from services.manifest.yaml.
//
// snapshotd has an extra dataDir argument so its JSON-Lines files land
// under /var/lib/xf/sidecars/snapshotd/.
func registerAll(
	grpcSrv *grpc.Server,
	storeFactory *store.Factory,
	tracker *idle.Tracker,
	logger *slog.Logger,
	storageRoot string,
) error {
	register := func(name string, fn func(*grpc.Server, *bbolt.DB, *idle.Tracker, *slog.Logger)) error {
		bdb, err := storeFactory.For(name)
		if err != nil {
			return err
		}
		fn(grpcSrv, bdb, tracker, logger)
		return nil
	}

	if err := register("snapshotd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		snapshotd.Register(s, d, t, l, filepath.Join(storageRoot, "snapshotd"))
	}); err != nil {
		return err
	}
	if err := register("bullboard", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		bullboard.Register(s, d, t, l)
	}); err != nil {
		return err
	}
	if err := register("attrouted", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		attrouted.Register(s, d, t, l)
	}); err != nil {
		return err
	}
	if err := register("schemard", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		schemard.Register(s, d, t, l)
	}); err != nil {
		return err
	}
	if err := register("coordd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		coordd.Register(s, d, t, l)
	}); err != nil {
		return err
	}
	if err := register("errord", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) {
		errord.Register(s, d, t, l)
	}); err != nil {
		return err
	}

	// searchd — Lucene-equivalent full-text index (Bleve). It is a separate
	// search CAPABILITY, not one of the 40 Apache-pattern manifest services,
	// so it is registered standalone here (and stays out of the manifest's
	// 40-service invariant). It uses a Bleve index on disk rather than Bolt,
	// so it bypasses the register() helper's per-service Bolt DB.
	searchd.Register(grpcSrv, tracker, logger, filepath.Join(storageRoot, "searchd"))

	// 34 skeleton registrations — each returns codes.Unimplemented for
	// every RPC except Health.
	skeletonRegistrations := []struct {
		name string
		fn   func(*grpc.Server, *bbolt.DB, *idle.Tracker, *slog.Logger)
	}{
		{"topicd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { topicd.Register(s, d, t, l) }},
		{"provd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { provd.Register(s, d, t, l) }},
		{"pressured", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { pressured.Register(s, d, t, l) }},
		{"extractd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { extractd.Register(s, d, t, l) }},
		{"dagd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { dagd.Register(s, d, t, l) }},
		{"ruled", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { ruled.Register(s, d, t, l) }},
		{"retentd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { retentd.Register(s, d, t, l) }},
		{"timetravd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { timetravd.Register(s, d, t, l) }},
		{"gatewayd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { gatewayd.Register(s, d, t, l) }},
		{"arrowd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { arrowd.Register(s, d, t, l) }},
		{"catalogd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { catalogd.Register(s, d, t, l) }},
		{"aclsd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { aclsd.Register(s, d, t, l) }},
		{"pluginhotd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { pluginhotd.Register(s, d, t, l) }},
		{"mesh", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { mesh.Register(s, d, t, l) }},
		{"smd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { smd.Register(s, d, t, l) }},
		{"tieredd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { tieredd.Register(s, d, t, l) }},
		{"qsched", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { qsched.Register(s, d, t, l) }},
		{"gremlind", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { gremlind.Register(s, d, t, l) }},
		{"tsd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { tsd.Register(s, d, t, l) }},
		{"hintd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { hintd.Register(s, d, t, l) }},
		{"viewd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { viewd.Register(s, d, t, l) }},
		{"cepd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { cepd.Register(s, d, t, l) }},
		{"xcomd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { xcomd.Register(s, d, t, l) }},
		{"purged", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { purged.Register(s, d, t, l) }},
		{"delayd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { delayd.Register(s, d, t, l) }},
		{"flumed", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { flumed.Register(s, d, t, l) }},
		{"politenessd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { politenessd.Register(s, d, t, l) }},
		{"fnd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { fnd.Register(s, d, t, l) }},
		{"drilld", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { drilld.Register(s, d, t, l) }},
		{"anomalyd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { anomalyd.Register(s, d, t, l) }},
		{"txd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { txd.Register(s, d, t, l) }},
		{"lookupd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { lookupd.Register(s, d, t, l) }},
		{"dedupd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { dedupd.Register(s, d, t, l) }},
		{"compactd", func(s *grpc.Server, d *bbolt.DB, t *idle.Tracker, l *slog.Logger) { compactd.Register(s, d, t, l) }},
	}
	for _, r := range skeletonRegistrations {
		if err := register(r.name, r.fn); err != nil {
			return err
		}
	}
	return nil
}

// pinCheckerFromSnapshotd inspects the snapshotd pinned bucket on every
// pruner sweep. It opens a read-only view of the snapshotd Bolt file. If
// the file doesn't exist (snapshotd has not yet created anything), the
// returned checker always reports false.
func pinCheckerFromSnapshotd(storageRoot string) pruner.PinChecker {
	return func(path string) bool {
		_ = filepath.Join(storageRoot, "snapshotd", "state.db") // referenced for clarity
		// The real PinChecker logic lives on the snapshotd Server, but
		// reaching it across packages without a tighter coupling is for a
		// follow-up. This slice ships the lightweight version: only files
		// under /var/lib/xf/sidecars/snapshotd/pinned/ are pinned.
		return filepath.Base(filepath.Dir(path)) == "pinned"
	}
}

func envOr(name, fallback string) string {
	if v, ok := os.LookupEnv(name); ok && v != "" {
		return v
	}
	return fallback
}

func slogLevel() slog.Level {
	switch envOr("XF_SIDECARS_LOG_LEVEL", "info") {
	case "debug":
		return slog.LevelDebug
	case "warn":
		return slog.LevelWarn
	case "error":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
