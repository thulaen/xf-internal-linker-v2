// Slice 1.6 — one-shot generator that reads services.manifest.yaml and
// writes a thin .proto skeleton for every service NOT already covered by a
// hand-written file in api/.
//
// Run from services/sidecars/:
//   go run ./cmd/gen-proto-skeletons
//
// The 6 critical services (snapshotd, bullboard, attrouted, schemard, coordd,
// errord) have hand-written .proto files with full message bodies; the
// generator skips them.

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"xf-internal-linker-v2/services/sidecars/internal/shared/manifest"
)

// commonMessages lives in shared.proto and is referenced by-name from every
// skeleton. The generator never re-declares these.
var commonMessages = map[string]bool{
	"Empty": true, "Ack": true, "HealthReply": true,
}

// alreadyHandWritten — these have rich .proto files; skip them.
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
		path := filepath.Join("api", svc.Name+".proto")
		if _, err := os.Stat(path); err == nil {
			fmt.Println("skip (exists):", path)
			continue
		}
		body := renderSkeleton(svc)
		// #nosec G306 -- this writes checked-in proto templates, which should be readable by the repo user.
		if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "write:", err)
			os.Exit(1)
		}
		fmt.Println("wrote:", path)
	}
}

func renderSkeleton(svc manifest.ServiceSpec) string {
	var sb strings.Builder
	prefix := capitalize(svc.Name) // service-prefix every message to avoid cross-file name collisions
	fmt.Fprintf(&sb, "// Slice 1.6 — %s skeleton contract.\n", svc.Name)
	fmt.Fprintf(&sb, "// Apache reference: %s. Owning Django module: %s.\n", svc.Apache, svc.OwningModule)
	sb.WriteString("// Ships as a gRPC skeleton this slice; every RPC returns codes.Unimplemented.\n")
	sb.WriteString("// Real RPC bodies fill in via a future session — tracked in the paper-trail under\n")
	sb.WriteString("// the tag `sidecars_followup`. Message names are service-prefixed because every\n")
	sb.WriteString("// .proto file lives in the same proto package (xf.sidecars.v1).\n\n")
	sb.WriteString("syntax = \"proto3\";\n\n")
	sb.WriteString("package xf.sidecars.v1;\n\n")
	sb.WriteString("import \"shared.proto\";\n\n")
	sb.WriteString("option go_package = \"xf-internal-linker-v2/services/sidecars/api/gen;sidecarsv1\";\n\n")

	fmt.Fprintf(&sb, "service %s {\n", prefix)
	for _, rpc := range svc.RPCs {
		writeRPC(&sb, prefix, rpc)
	}
	sb.WriteString("}\n\n")

	// Collect and dedupe the message names so we declare each once.
	seen := make(map[string]bool)
	names := make([]string, 0)
	for _, rpc := range svc.RPCs {
		for _, msg := range []string{rpc.In, rpc.Out} {
			if commonMessages[msg] {
				continue
			}
			prefixed := prefix + msg
			if !seen[prefixed] {
				seen[prefixed] = true
				names = append(names, prefixed)
			}
		}
	}
	sort.Strings(names)
	for _, n := range names {
		fmt.Fprintf(&sb, "message %s {}\n", n)
	}
	return sb.String()
}

func writeRPC(sb *strings.Builder, prefix string, rpc manifest.RPC) {
	in := rpc.In
	out := rpc.Out
	if !commonMessages[in] {
		in = prefix + in
	}
	if !commonMessages[out] {
		out = prefix + out
	}
	var stream string
	switch rpc.Streaming {
	case "server":
		stream = "returns (stream " + out + ")"
	case "client":
		fmt.Fprintf(sb, "  rpc %s(stream %s) returns (%s);\n", rpc.Name, in, out)
		return
	case "bidi":
		fmt.Fprintf(sb, "  rpc %s(stream %s) returns (stream %s);\n", rpc.Name, in, out)
		return
	default:
		stream = "returns (" + out + ")"
	}
	fmt.Fprintf(sb, "  rpc %s(%s) %s;\n", rpc.Name, in, stream)
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
