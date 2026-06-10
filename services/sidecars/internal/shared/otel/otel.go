// Package otel starts the localhost-only HTTP server that hosts pprof and
// the /healthz liveness endpoint. The port defaults to 6061 (from
// budget.yaml) so it does not collide with streamd's pprof on 6060.
//
// The healthcheck handler exposes a simple JSON body so the
// sidecars-healthcheck binary can dial via the gRPC Health RPC. The
// localhost /healthz is a developer convenience; production health is the
// gRPC Health RPC the Docker healthcheck binary uses.
//
// References:
//   - https://pkg.go.dev/net/http/pprof
//   - docs/specs/fr-sidecars-host.md (metrics_port = 6061, localhost-only)
package otel

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	_ "net/http/pprof" // localhost-only pprof endpoint
	"runtime"
	"time"
)

const (
	DefaultAddr            = "127.0.0.1:6061"
	CPUProfileRateHz       = 500
	defaultReadHeaderLimit = 5 * time.Second
	defaultShutdownGrace   = 2 * time.Second
)

var setCPUProfileRate = runtime.SetCPUProfileRate

// HealthReporter returns the current health state. Simple wrapper so the
// sidecars binary can plug in a real check (e.g., "every registered service
// has a healthy bolt.DB").
type HealthReporter func() (status string, ok bool)

// Options is the constructor input.
type Options struct {
	Addr           string
	HealthReporter HealthReporter
	Logger         *slog.Logger
}

// Server wraps the http.Server holding /healthz + pprof.
type Server struct {
	srv    *http.Server
	logger *slog.Logger
}

// Start builds and starts the server in a goroutine. Returns the Server so
// callers can Shutdown gracefully.
func Start(opts Options) *Server {
	setCPUProfileRate(CPUProfileRateHz)
	if opts.Addr == "" {
		opts.Addr = DefaultAddr
	}
	if opts.Logger == nil {
		opts.Logger = slog.Default()
	}
	if opts.HealthReporter == nil {
		opts.HealthReporter = func() (string, bool) { return "ok", true }
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", buildHealthHandler(opts.HealthReporter))
	// net/http/pprof has already registered its handlers on http.DefaultServeMux
	// via its init(). We mount the default mux at /debug/pprof/ so our /healthz
	// path stays clean.
	mux.Handle("/debug/pprof/", http.DefaultServeMux)
	mux.Handle("/debug/pprof", http.DefaultServeMux)

	srv := &http.Server{
		Addr:              opts.Addr,
		Handler:           mux,
		ReadHeaderTimeout: defaultReadHeaderLimit,
	}
	s := &Server{srv: srv, logger: opts.Logger}
	go s.run()
	return s
}

func (s *Server) run() {
	s.logger.Info("otel http endpoint up", "addr", s.srv.Addr)
	if err := s.srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		s.logger.Warn("otel http server error", "err", err)
	}
}

// Shutdown stops the server gracefully.
func (s *Server) Shutdown(ctx context.Context) error {
	return s.srv.Shutdown(ctx)
}

// Addr returns the address the server bound to.
func (s *Server) Addr() string {
	return s.srv.Addr
}

func buildHealthHandler(reporter HealthReporter) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		status, ok := reporter()
		w.Header().Set("content-type", "application/json")
		if !ok {
			w.WriteHeader(http.StatusServiceUnavailable)
		}
		_, _ = fmt.Fprintf(w, `{"status":%q}`, status)
	}
}
