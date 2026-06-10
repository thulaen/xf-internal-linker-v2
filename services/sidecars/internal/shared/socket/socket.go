// Package socket opens the one Unix-domain socket the 40 sidecar services
// share. Different gRPC service names route to different internal handlers
// off the same listener.
//
// The socket path defaults to /var/run/xf/sidecars.sock and is overridable
// via XF_SIDECARS_SOCKET. Permissions are 0660 so the backend container's
// non-root user can dial it through the shared `sidecars_sock` named volume.
//
// References:
//   - man 7 unix — AF_UNIX socket semantics
//   - https://grpc.io/docs/guides/naming/ (unix:// scheme)
//   - services/streamd/cmd/streamd/main.go — same pattern, single service
package socket

import (
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
)

const (
	DefaultPath = "/var/run/xf/sidecars.sock"
	// DefaultMode is 0o666 (not the strict 0o660 used by streamd) because
	// the socket file lives inside a Docker named volume mounted by exactly
	// two containers — sidecars itself and backend. Sidecars runs as root
	// because Docker named volumes are root-owned by default (see the
	// inline comment on the `streamd` service in docker-compose.yml that
	// explains why `user: 1000:1000` is not viable for sidecar processes
	// that need to write into a named volume), while backend runs as
	// uid 1000:1000 (appuser). With 0o660 the backend cannot connect to a
	// root-owned socket; 0o666 fixes that. The blast radius is identical
	// because the volume is not exposed outside those two containers.
	DefaultMode = 0o666
	DefaultDir  = 0o755
)

// EnsureParentDir creates the directory holding the socket if it does not
// exist. Mode is 0755 so the backend container's user can list it.
func EnsureParentDir(path string) error {
	dir := filepath.Dir(path)
	if dir == "" {
		return nil
	}
	if err := os.MkdirAll(dir, DefaultDir); err != nil {
		return fmt.Errorf("ensure socket dir %q: %w", dir, err)
	}
	return nil
}

// RemoveStale deletes any leftover socket file from a prior unclean shutdown.
// A nonexistent file is not an error.
func RemoveStale(path string) error {
	if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("remove stale socket %q: %w", path, err)
	}
	return nil
}

// Listen binds the Unix-domain socket at path. It ensures the parent dir
// exists, removes any leftover socket file, listens, and chmod's the
// resulting file to mode 0660. The caller is responsible for closing the
// returned net.Listener and removing the socket file on shutdown.
func Listen(path string) (net.Listener, error) {
	if path == "" {
		return nil, errors.New("socket: path is required")
	}
	if err := EnsureParentDir(path); err != nil {
		return nil, err
	}
	if err := RemoveStale(path); err != nil {
		return nil, err
	}
	ln, err := net.Listen("unix", path)
	if err != nil {
		return nil, fmt.Errorf("listen unix %q: %w", path, err)
	}
	if err := os.Chmod(path, DefaultMode); err != nil {
		_ = ln.Close()
		return nil, fmt.Errorf("chmod %q: %w", path, err)
	}
	return ln, nil
}
