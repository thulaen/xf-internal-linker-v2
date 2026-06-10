// Package manifest reads services.manifest.yaml + budget.yaml and validates
// the result against the 7 hard constraints from
// docs/specs/fr-sidecars-host.md.
//
// The manifest is the single source of truth for which sidecar services
// exist, their owning Django module, their nominal RAM/storage shares, and
// their priority. cmd/sidecars/main.go reads it at boot and registers each
// service against the shared gRPC server.
//
// References:
//   - https://pkg.go.dev/gopkg.in/yaml.v3
//   - docs/specs/fr-sidecars-host.md
package manifest

import (
	"errors"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// MaxServices is the cap from docs/specs/fr-sidecars-host.md.
const MaxServices = 40

// Manifest is the parsed services.manifest.yaml.
type Manifest struct {
	Host     HostConfig    `yaml:"host"`
	Services []ServiceSpec `yaml:"services"`
}

// HostConfig declares the global cap.
type HostConfig struct {
	TotalMemoryMB                  int    `yaml:"total_memory_mb"`
	TotalStorageMB                 int    `yaml:"total_storage_mb"`
	RetentionHours                 int    `yaml:"retention_hours"`
	MaxImageSizeMB                 int    `yaml:"max_image_size_mb"`
	SocketPath                     string `yaml:"socket_path"`
	StoragePath                    string `yaml:"storage_path"`
	MetricsPort                    int    `yaml:"metrics_port"`
	IdleReleaseSeconds             int    `yaml:"idle_release_seconds"`
	PrunerIntervalSeconds          int    `yaml:"pruner_interval_seconds"`
	MemoryPressureThresholdPercent int    `yaml:"memory_pressure_threshold_percent"`
}

// ServiceSpec is one row in the services list.
type ServiceSpec struct {
	Name           string   `yaml:"name"`
	Apache         string   `yaml:"apache"`
	OwningModule   string   `yaml:"owning_module"`
	MemoryShareMB  int      `yaml:"memory_share_mb"`
	StorageShareMB int      `yaml:"storage_share_mb"`
	Priority       string   `yaml:"priority"` // high | medium | low
	RPCs           []RPC    `yaml:"rpcs"`
	Implemented    bool     `yaml:"implemented"`
	FollowUpTags   []string `yaml:"follow_up_tags,omitempty"`
}

// RPC declares one gRPC method.
type RPC struct {
	Name      string `yaml:"name"`
	In        string `yaml:"in"`
	Out       string `yaml:"out"`
	Streaming string `yaml:"streaming"` // none | server | client | bidi
}

// validPriorities is the closed set the spec allows.
var validPriorities = map[string]bool{"high": true, "medium": true, "low": true}

// validStreaming is the closed set the spec allows.
var validStreaming = map[string]bool{"": true, "none": true, "server": true, "client": true, "bidi": true}

// Load reads a YAML file from disk and returns a validated Manifest.
func Load(path string) (*Manifest, error) {
	// #nosec G304 -- sidecar manifests are operator-supplied local config files, not request-controlled paths.
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read manifest %q: %w", path, err)
	}
	return Parse(raw)
}

// Parse reads YAML bytes and returns a validated Manifest.
func Parse(raw []byte) (*Manifest, error) {
	var m Manifest
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("unmarshal manifest: %w", err)
	}
	if err := m.Validate(); err != nil {
		return nil, err
	}
	return &m, nil
}

// Validate enforces the 7 hard constraints + manifest schema.
func (m *Manifest) Validate() error {
	var errs []error
	if m.Host.TotalMemoryMB <= 0 {
		errs = append(errs, errors.New("host.total_memory_mb must be > 0"))
	}
	if m.Host.TotalStorageMB <= 0 {
		errs = append(errs, errors.New("host.total_storage_mb must be > 0"))
	}
	if m.Host.RetentionHours <= 0 {
		errs = append(errs, errors.New("host.retention_hours must be > 0"))
	}
	if m.Host.SocketPath == "" {
		errs = append(errs, errors.New("host.socket_path is required"))
	}
	if m.Host.StoragePath == "" {
		errs = append(errs, errors.New("host.storage_path is required"))
	}
	if len(m.Services) == 0 {
		errs = append(errs, errors.New("services list is empty"))
	}
	if len(m.Services) > MaxServices {
		errs = append(errs, fmt.Errorf("services count %d exceeds MaxServices %d", len(m.Services), MaxServices))
	}
	seen := make(map[string]bool, len(m.Services))
	for i, s := range m.Services {
		prefix := fmt.Sprintf("services[%d](%s)", i, s.Name)
		if s.Name == "" {
			errs = append(errs, fmt.Errorf("%s: name is required", prefix))
			continue
		}
		if seen[s.Name] {
			errs = append(errs, fmt.Errorf("%s: duplicate name", prefix))
		}
		seen[s.Name] = true
		if s.OwningModule == "" {
			errs = append(errs, fmt.Errorf("%s: owning_module is required", prefix))
		}
		if !validPriorities[s.Priority] {
			errs = append(errs, fmt.Errorf("%s: priority %q invalid (want high|medium|low)", prefix, s.Priority))
		}
		if len(s.RPCs) == 0 {
			errs = append(errs, fmt.Errorf("%s: rpcs list is empty", prefix))
		}
		for j, r := range s.RPCs {
			if r.Name == "" {
				errs = append(errs, fmt.Errorf("%s.rpcs[%d]: name is required", prefix, j))
			}
			if !validStreaming[r.Streaming] {
				errs = append(errs, fmt.Errorf("%s.rpcs[%d](%s): streaming %q invalid", prefix, j, r.Name, r.Streaming))
			}
		}
	}
	return errors.Join(errs...)
}

// ImplementedServices returns the subset marked implemented=true. Used by
// tests + the cmd/sidecars status line at boot.
func (m *Manifest) ImplementedServices() []ServiceSpec {
	out := make([]ServiceSpec, 0, len(m.Services))
	for _, s := range m.Services {
		if s.Implemented {
			out = append(out, s)
		}
	}
	return out
}

// SkeletonServices returns the complement of ImplementedServices.
func (m *Manifest) SkeletonServices() []ServiceSpec {
	out := make([]ServiceSpec, 0, len(m.Services))
	for _, s := range m.Services {
		if !s.Implemented {
			out = append(out, s)
		}
	}
	return out
}
