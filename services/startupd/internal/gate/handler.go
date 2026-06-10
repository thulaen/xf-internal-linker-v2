package gate

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// quota holds the Layer 2 AutoIssue and PaperTrail minimums for one session type.
type quota struct {
	AutoIssues int
	PaperTrail int
}

var layer2Quotas = map[string]quota{
	"docs":           {0, 0},
	"infrastructure": {20, 5},
	"reconciliation": {10, 3},
	"feature":        {103, 10},
}

// djangoCacheTTL bounds how long a Django session-gate response is reused before
// the next request re-queries the backend. Repeat rituals (same session type +
// areas) within this window skip the Django round-trip and return instantly; the
// HMAC token is still re-signed on every request so nothing downstream breaks.
const djangoCacheTTL = 45 * time.Second

type cachedDjango struct {
	dr      djangoResponse
	expires time.Time
}

// djangoCache is a tiny TTL cache of Django session-gate responses, keyed by
// session type + areas. It is safe for concurrent use.
type djangoCache struct {
	mu      sync.Mutex
	ttl     time.Duration
	entries map[string]cachedDjango
}

func newDjangoCache(ttl time.Duration) *djangoCache {
	return &djangoCache{ttl: ttl, entries: make(map[string]cachedDjango)}
}

func (c *djangoCache) get(key string, now time.Time) (djangoResponse, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.entries[key]
	if !ok || !now.Before(entry.expires) {
		return djangoResponse{}, false
	}
	return entry.dr, true
}

func (c *djangoCache) put(key string, dr djangoResponse, now time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries[key] = cachedDjango{dr: dr, expires: now.Add(c.ttl)}
}

// cacheKey is order-insensitive over areas so [a,b] and [b,a] share one entry.
func cacheKey(sessionType string, areas []string) string {
	sorted := append([]string(nil), areas...)
	sort.Strings(sorted)
	return sessionType + "\x00" + strings.Join(sorted, "\x00")
}

// Config holds all injectable dependencies for the gate handler.
type Config struct {
	DjangoURL  string       // base URL of the Django backend (no trailing slash)
	Secret     string       // SESSION_GATE_SECRET for HMAC signing
	StatePath  string       // path to write audit/session_gate_state.json
	HTTPClient *http.Client // nil falls back to http.DefaultClient
	Now        func() time.Time
}

type djangoResponse struct {
	Markers struct {
		Sticky       string `json:"sticky"`
		Registry     string `json:"registry"`
		PaperTrail   string `json:"paper_trail"`
		Snapshots    string `json:"snapshots"`
		Lessons      string `json:"lessons"`
		TDDPreflight string `json:"tdd_preflight"`
	} `json:"markers"`
	TotalOpenCount int `json:"total_open_count"`
}

type stateJSON struct {
	SessionType      string `json:"session_type"`
	Layer2AutoIssues int    `json:"layer2_autoissues"`
	Layer2PaperTrail int    `json:"layer2_paper_trail"`
	Token            string `json:"token"`
	TS               int64  `json:"ts"`
	TotalOpenCount   int    `json:"total_open_count"`
	GeneratedAt      string `json:"generated_at"`
}

// Handler returns an http.HandlerFunc for GET /gate?type=<sessionType>&area=<area>.
// The handler:
//  1. Validates the session type (400 on unknown).
//  2. Proxies to Django for the six database-backed markers (502 on failure).
//  3. Computes an HMAC-SHA256 token so hooks can verify the marker came from startupd.
//  4. Writes session_gate_state.json to cfg.StatePath.
//  5. Returns JSON: { marker_block, state }.
func Handler(cfg Config) http.HandlerFunc {
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = http.DefaultClient
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	cache := newDjangoCache(djangoCacheTTL)
	return func(w http.ResponseWriter, r *http.Request) {
		sessionType := r.URL.Query().Get("type")
		q, ok := layer2Quotas[sessionType]
		if !ok {
			http.Error(w,
				"unknown session type; valid values: docs, infrastructure, reconciliation, feature",
				http.StatusBadRequest,
			)
			return
		}

		areas := r.URL.Query()["area"]
		now := cfg.Now()

		// Repeat rituals (same session type + areas) within the TTL reuse the
		// cached Django markers and skip the round-trip; the token below is still
		// re-signed from `now` on every request so the gate state stays fresh.
		key := cacheKey(sessionType, areas)
		dr, hit := cache.get(key, now)
		if !hit {
			fetched, err := proxyDjango(cfg.HTTPClient, cfg.DjangoURL, sessionType, areas)
			if err != nil {
				http.Error(w, "django session-gate unavailable: "+err.Error(), http.StatusBadGateway)
				return
			}
			dr = fetched
			cache.put(key, dr, now)
		}

		tsMins := now.Unix() / 60
		token := computeToken(cfg.Secret, sessionType, tsMins, dr.TotalOpenCount)
		generatedAt := now.UTC().Format(time.RFC3339)

		state := stateJSON{
			SessionType:      sessionType,
			Layer2AutoIssues: q.AutoIssues,
			Layer2PaperTrail: q.PaperTrail,
			Token:            token,
			TS:               tsMins,
			TotalOpenCount:   dr.TotalOpenCount,
			GeneratedAt:      generatedAt,
		}

		if err := writeStateFile(cfg.StatePath, state); err != nil {
			http.Error(w, "could not write session_gate_state.json: "+err.Error(), http.StatusInternalServerError)
			return
		}

		block := buildMarkerBlock(&dr, token, tsMins)
		resp := struct {
			MarkerBlock string    `json:"marker_block"`
			State       stateJSON `json:"state"`
		}{MarkerBlock: block, State: state}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}
}

func proxyDjango(client *http.Client, baseURL, sessionType string, areas []string) (djangoResponse, error) {
	params := url.Values{}
	params.Set("type", sessionType)
	for _, a := range areas {
		params.Add("area", a)
	}
	target := strings.TrimRight(baseURL, "/") + "/api/session-gate/?" + params.Encode()
	resp, err := client.Get(target)
	if err != nil {
		return djangoResponse{}, err
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return djangoResponse{}, err
	}
	var dr djangoResponse
	if err := json.Unmarshal(body, &dr); err != nil {
		return djangoResponse{}, fmt.Errorf("invalid django response: %w", err)
	}
	return dr, nil
}

// computeToken returns the first 16 hex chars of HMAC-SHA256(secret, msg).
// msg format: "sessionType|unixMinute|totalOpenCount" — agreed with the Python hook.
func computeToken(secret, sessionType string, tsMins int64, totalOpen int) string {
	msg := fmt.Sprintf("%s|%d|%d", sessionType, tsMins, totalOpen)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(msg))
	return hex.EncodeToString(mac.Sum(nil))[:16]
}

func writeStateFile(path string, state stateJSON) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o600)
}

func buildMarkerBlock(dr *djangoResponse, token string, tsMins int64) string {
	sourceMarker := fmt.Sprintf("[SESSION GATE SOURCE: startupd token=%s ts=%d]", token, tsMins)
	return strings.Join([]string{
		dr.Markers.Sticky,
		dr.Markers.Registry,
		dr.Markers.PaperTrail,
		dr.Markers.Snapshots,
		dr.Markers.Lessons,
		dr.Markers.TDDPreflight,
		sourceMarker,
	}, "\n")
}
