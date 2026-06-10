package main

import (
	"errors"
	"log"
	"net/http"
	"net/http/pprof"
	"os"
	"time"

	"xf-internal-linker-v2/services/startupd/internal/gate"
	"xf-internal-linker-v2/services/startupd/internal/payload"
)

const (
	readHeaderTimeout = 5 * time.Second
	readTimeout       = 10 * time.Second
	writeTimeout      = 10 * time.Second
	idleTimeout       = 30 * time.Second
)

func main() {
	addr := envOr("XF_STARTUPD_ADDR", ":8765")
	path := envOr("XF_STARTUP_PAYLOAD_PATH", "/repo/audit/session_start_payload.jsonl")
	gateCfg := gate.Config{
		DjangoURL: envOr("XF_GATE_DJANGO_URL", "http://backend:8000"),
		Secret:    envOr("SESSION_GATE_SECRET", ""),
		StatePath: envOr("XF_GATE_STATE_PATH", "/repo/audit/session_gate_state.json"),
	}
	log.Printf("startupd listening on %s payload=%s", addr, path)
	if err := newServer(addr, path, gateCfg).ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}

func newServer(addr string, path string, gateCfg gate.Config) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           newMux(path, gateCfg),
		ReadHeaderTimeout: readHeaderTimeout,
		ReadTimeout:       readTimeout,
		WriteTimeout:      writeTimeout,
		IdleTimeout:       idleTimeout,
	}
}

func newMux(path string, gateCfg gate.Config) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/payload", payloadHandler(path))
	mux.HandleFunc("/gate", gate.Handler(gateCfg))
	mux.HandleFunc("/debug/pprof/", pprof.Index)
	mux.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
	mux.HandleFunc("/debug/pprof/profile", pprof.Profile)
	mux.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
	mux.HandleFunc("/debug/pprof/trace", pprof.Trace)
	return mux
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok\n"))
}

func payloadHandler(path string) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		data, err := payload.LoadLatest(path)
		if err != nil {
			if errors.Is(err, payload.ErrPayloadMissing) {
				http.Error(w, "startup payload missing", http.StatusNotFound)
				return
			}
			http.Error(w, "startup payload unreadable", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(data)
	}
}

func envOr(name string, fallback string) string {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	return value
}
