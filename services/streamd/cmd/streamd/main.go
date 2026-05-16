// Slice 1.5 — streamd binary entry point.
//
// Boots a gRPC server over a Unix-domain socket. The socket path defaults to
// /var/run/xf/streamd.sock (overridable via XF_STREAMD_SOCKET). The bound
// listener is shared via the streamd_sock named Docker volume so the backend
// container's private Python client can dial it.
//
// References:
//   - Donovan & Kernighan 2015 §8 (concurrency), §11 (testing)
//   - https://pkg.go.dev/os/signal#NotifyContext
//   - https://pkg.go.dev/log/slog
//   - https://grpc.io/docs/languages/go/
//   - man 7 unix — AF_UNIX socket semantics

package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	_ "net/http/pprof" // localhost-only pprof endpoint
	"os"
	"os/signal"
	"strconv"
	"sync"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/keepalive"

	streamdv1 "xf-internal-linker-v2/services/streamd/api/gen"
	"xf-internal-linker-v2/services/streamd/internal/broker"
)

const (
	defaultSocketPath        = "/var/run/xf/streamd.sock"
	defaultSocketMode        = 0o660
	defaultPprofAddr         = "127.0.0.1:6060"
	defaultMaxTopics         = 128
	defaultBufferedPerTopic  = 4096
	defaultMaxMsgBytes       = 4 << 20 // 4 MB
	defaultKeepaliveTime     = 30 * time.Second
	gracefulShutdownDeadline = 2 * time.Second
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slogLevel()}))
	slog.SetDefault(logger)

	socketPath := envOr("XF_STREAMD_SOCKET", defaultSocketPath)
	bounds := broker.Bounds{
		MaxTopics:                 envInt("XF_STREAMD_MAX_TOPICS", defaultMaxTopics),
		MaxBufferedEventsPerTopic: envInt("XF_STREAMD_BUFFERED_PER_TOPIC", defaultBufferedPerTopic),
	}
	pprofAddr := envOr("XF_STREAMD_PPROF_ADDR", defaultPprofAddr)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, logger, socketPath, bounds, pprofAddr); err != nil {
		logger.Error("streamd terminated with error", "err", err)
		os.Exit(1)
	}
	logger.Info("streamd shutdown clean")
}

func run(
	ctx context.Context,
	logger *slog.Logger,
	socketPath string,
	bounds broker.Bounds,
	pprofAddr string,
) error {
	if err := os.MkdirAll(parentDir(socketPath), 0o755); err != nil {
		return fmt.Errorf("ensure socket dir: %w", err)
	}
	// A previous unclean shutdown can leave the socket file in place.
	_ = os.Remove(socketPath)

	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("listen unix %q: %w", socketPath, err)
	}
	if err := os.Chmod(socketPath, defaultSocketMode); err != nil {
		return fmt.Errorf("chmod %q: %w", socketPath, err)
	}
	logger.Info("streamd bound", "socket", socketPath, "mode", "0660")

	brokerImpl := broker.New(bounds)
	server := newStreamdServer(brokerImpl, logger)
	grpcSrv := grpc.NewServer(
		grpc.MaxRecvMsgSize(defaultMaxMsgBytes),
		grpc.MaxSendMsgSize(defaultMaxMsgBytes),
		grpc.KeepaliveParams(keepalive.ServerParameters{
			Time:    defaultKeepaliveTime,
			Timeout: 5 * time.Second,
		}),
	)
	streamdv1.RegisterStreamdServer(grpcSrv, server)

	// localhost-only pprof so OpenTelemetry profiles can sample without
	// exposing the surface outside the container.
	pprofSrv := startPprof(logger, pprofAddr)

	serveErr := make(chan error, 1)
	go func() {
		logger.Info("streamd serving", "addr", listener.Addr().String())
		serveErr <- grpcSrv.Serve(listener)
	}()

	select {
	case <-ctx.Done():
		logger.Info("streamd received shutdown signal")
	case err := <-serveErr:
		if err != nil && !errors.Is(err, grpc.ErrServerStopped) {
			return fmt.Errorf("grpc serve: %w", err)
		}
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), gracefulShutdownDeadline)
	defer cancel()
	stopped := make(chan struct{})
	go func() {
		grpcSrv.GracefulStop()
		close(stopped)
	}()
	select {
	case <-stopped:
		logger.Info("streamd graceful stop complete")
	case <-shutdownCtx.Done():
		logger.Warn("streamd graceful stop deadline exceeded; forcing stop")
		grpcSrv.Stop()
	}

	if pprofSrv != nil {
		if err := pprofSrv.Shutdown(shutdownCtx); err != nil {
			logger.Warn("pprof shutdown error", "err", err)
		}
	}

	if err := os.Remove(socketPath); err != nil && !errors.Is(err, os.ErrNotExist) {
		logger.Warn("could not remove socket file on exit", "socket", socketPath, "err", err)
	}
	return nil
}

func startPprof(logger *slog.Logger, addr string) *http.Server {
	if addr == "" || addr == "off" {
		return nil
	}
	srv := &http.Server{
		Addr:              addr,
		ReadHeaderTimeout: 5 * time.Second,
	}
	var once sync.Once
	go func() {
		once.Do(func() {
			logger.Info("streamd pprof endpoint up", "addr", addr)
		})
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Warn("pprof server error", "err", err)
		}
	}()
	return srv
}

func envOr(name, fallback string) string {
	if v, ok := os.LookupEnv(name); ok && v != "" {
		return v
	}
	return fallback
}

func envInt(name string, fallback int) int {
	if v, ok := os.LookupEnv(name); ok && v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			return parsed
		}
	}
	return fallback
}

func slogLevel() slog.Level {
	switch envOr("XF_STREAMD_LOG_LEVEL", "info") {
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

func parentDir(path string) string {
	for i := len(path) - 1; i >= 0; i-- {
		if path[i] == '/' {
			if i == 0 {
				return "/"
			}
			return path[:i]
		}
	}
	return "."
}
