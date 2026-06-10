// Slice 1.6 — one-shot generator that writes a thin internal/<name>/server.go
// for every skeleton service in services.manifest.yaml.
//
// Each generated file:
//   - Declares a Server type that embeds the generated UnimplementedXxxServer.
//   - Exposes Register(grpcServer, store, idleTracker, logger) which builds
//     the Server, registers it on the gRPC server, and registers it with
//     the idle tracker at the priority declared in the manifest.
//   - Implements Health() returning HEALTH_SERVING.
//   - Implements Idle() as a no-op stub (skeletons have no caches yet).
//
// Hand-written services keep their own server.go. The generator skips them.
//
// Run from services/sidecars/:
//   go run ./cmd/gen-server-skeletons

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"xf-internal-linker-v2/services/sidecars/internal/shared/manifest"
)

// alreadyHandWritten — same list as gen-proto-skeletons. Hand-written
// services have their own internal/<name>/server.go with real logic.
var alreadyHandWritten = map[string]bool{
	"snapshotd": true, "bullboard": true, "attrouted": true,
	"schemard": true, "coordd": true, "errord": true,
}

func main() {
	m, err := manifest.Load("services.manifest.yaml")
	if err != nil {
		fmt.Fprintln(os.Stderr, "load manifest:", err)
		os.Exit(1)
	}
	for _, svc := range m.Services {
		if alreadyHandWritten[svc.Name] {
			continue
		}
		dir := filepath.Join("internal", svc.Name)
		if err := os.MkdirAll(dir, 0o755); err != nil {
			fmt.Fprintln(os.Stderr, "mkdir:", err)
			os.Exit(1)
		}
		path := filepath.Join(dir, "server.go")
		if _, err := os.Stat(path); err == nil {
			fmt.Println("skip (exists):", path)
			continue
		}
		body := renderServer(svc)
		// #nosec G306 -- this writes checked-in source templates, which should be readable by the repo user.
		if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "write:", err)
			os.Exit(1)
		}
		fmt.Println("wrote:", path)
	}
}

func renderServer(svc manifest.ServiceSpec) string {
	pkg := svc.Name
	typ := capitalize(svc.Name)
	priority := priorityConst(svc.Priority)
	var sb strings.Builder
	fmt.Fprintf(&sb, "// Package %s is the gRPC skeleton for the %s sidecar service.\n", pkg, svc.Name)
	fmt.Fprintf(&sb, "// Apache reference: %s. Owning Django module: %s.\n", svc.Apache, svc.OwningModule)
	sb.WriteString("//\n")
	sb.WriteString("// Slice 1.6 ships this service as a skeleton: every RPC returns\n")
	sb.WriteString("// codes.Unimplemented. The full implementation lands in a future slice;\n")
	sb.WriteString("// paper-trail entry tagged `sidecars_followup` tracks the work.\n")
	fmt.Fprintf(&sb, "package %s\n\n", pkg)
	sb.WriteString("import (\n")
	sb.WriteString("\t\"context\"\n")
	sb.WriteString("\t\"log/slog\"\n")
	sb.WriteString("\t\"time\"\n\n")
	sb.WriteString("\t\"google.golang.org/grpc\"\n")
	sb.WriteString("\t\"go.etcd.io/bbolt\"\n\n")
	sb.WriteString("\tsidecarsv1 \"xf-internal-linker-v2/services/sidecars/api/gen\"\n")
	sb.WriteString("\t\"xf-internal-linker-v2/services/sidecars/internal/shared/idle\"\n")
	sb.WriteString(")\n\n")
	fmt.Fprintf(&sb, "// ServiceName is the canonical name used in the manifest, idle tracker, and logs.\nconst ServiceName = %q\n\n", svc.Name)

	// Server type
	fmt.Fprintf(&sb, "// Server is the gRPC handler for %s.\n", svc.Name)
	fmt.Fprintf(&sb, "type Server struct {\n")
	fmt.Fprintf(&sb, "\tsidecarsv1.Unimplemented%sServer\n", typ)
	sb.WriteString("\tstore     *bbolt.DB\n")
	sb.WriteString("\tlogger    *slog.Logger\n")
	sb.WriteString("\tstartedAt time.Time\n")
	sb.WriteString("}\n\n")

	// Register helper
	sb.WriteString("// Register wires the server onto the shared gRPC server + idle tracker.\n")
	sb.WriteString("func Register(grpcSrv *grpc.Server, db *bbolt.DB, tracker *idle.Tracker, logger *slog.Logger) *Server {\n")
	sb.WriteString("\ts := &Server{store: db, logger: logger.With(\"service\", ServiceName), startedAt: time.Now()}\n")
	fmt.Fprintf(&sb, "\tsidecarsv1.Register%sServer(grpcSrv, s)\n", typ)
	fmt.Fprintf(&sb, "\ttracker.Register(ServiceName, s, %s)\n", priority)
	sb.WriteString("\treturn s\n")
	sb.WriteString("}\n\n")

	// Idle stub
	sb.WriteString("// Idle releases caches under memory pressure. Skeleton: no-op.\n")
	sb.WriteString("func (s *Server) Idle() {}\n\n")

	// Health implementation — the one RPC every service answers.
	sb.WriteString("// Health returns HEALTH_SERVING. Skeletons answer Health so the\n")
	sb.WriteString("// sidecars-healthcheck binary can verify the gRPC server is up before any\n")
	sb.WriteString("// individual service is fully implemented.\n")
	sb.WriteString("func (s *Server) Health(_ context.Context, _ *sidecarsv1.Empty) (*sidecarsv1.HealthReply, error) {\n")
	sb.WriteString("\treturn &sidecarsv1.HealthReply{\n")
	sb.WriteString("\t\tStatus:    sidecarsv1.HealthStatus_HEALTH_SERVING,\n")
	sb.WriteString("\t\tStartedAt: s.startedAt.UTC().Format(time.RFC3339),\n")
	sb.WriteString("\t\tService:   ServiceName,\n")
	sb.WriteString("\t}, nil\n")
	sb.WriteString("}\n")
	return sb.String()
}

func priorityConst(p string) string {
	switch p {
	case "high":
		return "idle.PriorityHigh"
	case "low":
		return "idle.PriorityLow"
	default:
		return "idle.PriorityMedium"
	}
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
