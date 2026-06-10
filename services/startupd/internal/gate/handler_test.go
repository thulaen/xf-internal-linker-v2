package gate

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// fixedClock returns a stable time so token timestamps are deterministic.
func fixedClock() time.Time {
	return time.Date(2026, 5, 28, 12, 0, 0, 0, time.UTC)
}

// mockDjango stands in for the backend session-gate endpoint. It returns the
// six database-backed markers and the total open count the Go handler signs.
func mockDjango(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/session-gate/" {
			t.Errorf("unexpected proxy path: %s", r.URL.Path)
		}
		body := map[string]any{
			"markers": map[string]string{
				"sticky":        "[STICKY 1 READ: timestamp=2026-05-28T12:00:00Z sha256=abc123 agent=startupd]",
				"registry":      "[REGISTRY READ: 40 open (4 agent / 4 glitchtip / 4 pyroscope / 4 tempo / 4 loki / 4 faro / 4 mutation / 4 fuzz / 4 contract / 4 gh_ci) — picked: #1, #2, #3]",
				"paper_trail":   "[PAPER TRAIL READ: 12 open — picked: #10, #11, #12]",
				"snapshots":     "[SNAPSHOTS READ: 5 snapshots attached to 3 open issues — picked: #1(perf), #2(perf), #3(perf)]",
				"lessons":       "[LESSONS BEFORE START: 4 resolved-lesson rows reviewed in backend/apps/core]",
				"tdd_preflight": "[TDD PREFLIGHT: 5 categories armed]",
			},
			"total_open_count": 142,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(body)
	}))
}

func newTestConfig(t *testing.T, djangoURL string) Config {
	t.Helper()
	return Config{
		DjangoURL:  djangoURL,
		Secret:     "test-secret-key-0123456789abcdef",
		StatePath:  filepath.Join(t.TempDir(), "session_gate_state.json"),
		HTTPClient: &http.Client{Timeout: 5 * time.Second},
		Now:        fixedClock,
	}
}

func TestGateHandler_Reconciliation(t *testing.T) {
	django := mockDjango(t)
	defer django.Close()
	cfg := newTestConfig(t, django.URL)

	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	resp, err := http.Get(server.URL + "/gate?type=reconciliation&area=backend/apps/core")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", resp.StatusCode)
	}

	var out struct {
		MarkerBlock string `json:"marker_block"`
		State       struct {
			SessionType      string `json:"session_type"`
			Layer2AutoIssues int    `json:"layer2_autoissues"`
			Layer2PaperTrail int    `json:"layer2_paper_trail"`
			Token            string `json:"token"`
		} `json:"state"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatal(err)
	}

	wantPrefixes := []string{
		"[STICKY 1 READ:",
		"[REGISTRY READ:",
		"[PAPER TRAIL READ:",
		"[SNAPSHOTS READ:",
		"[LESSONS BEFORE START:",
		"[TDD PREFLIGHT:",
		"[SESSION GATE SOURCE: startupd token=",
	}
	for _, prefix := range wantPrefixes {
		if !strings.Contains(out.MarkerBlock, prefix) {
			t.Errorf("marker_block missing %q\n---\n%s", prefix, out.MarkerBlock)
		}
	}

	if out.State.SessionType != "reconciliation" {
		t.Errorf("session_type = %q, want reconciliation", out.State.SessionType)
	}
	if out.State.Layer2AutoIssues != 10 {
		t.Errorf("layer2_autoissues = %d, want 10", out.State.Layer2AutoIssues)
	}
	if out.State.Layer2PaperTrail != 3 {
		t.Errorf("layer2_paper_trail = %d, want 3", out.State.Layer2PaperTrail)
	}
}

func TestGateHandler_QuotaScaling(t *testing.T) {
	django := mockDjango(t)
	defer django.Close()
	cfg := newTestConfig(t, django.URL)
	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	cases := []struct {
		sessionType    string
		wantAutoIssues int
		wantPaperTrail int
	}{
		{"docs", 0, 0},
		{"infrastructure", 20, 5},
		{"reconciliation", 10, 3},
		{"feature", 103, 10},
	}
	for _, tc := range cases {
		t.Run(tc.sessionType, func(t *testing.T) {
			resp, err := http.Get(server.URL + "/gate?type=" + tc.sessionType)
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = resp.Body.Close() }()

			var out struct {
				State struct {
					Layer2AutoIssues int `json:"layer2_autoissues"`
					Layer2PaperTrail int `json:"layer2_paper_trail"`
				} `json:"state"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
				t.Fatal(err)
			}
			if out.State.Layer2AutoIssues != tc.wantAutoIssues {
				t.Errorf("%s layer2_autoissues = %d, want %d", tc.sessionType, out.State.Layer2AutoIssues, tc.wantAutoIssues)
			}
			if out.State.Layer2PaperTrail != tc.wantPaperTrail {
				t.Errorf("%s layer2_paper_trail = %d, want %d", tc.sessionType, out.State.Layer2PaperTrail, tc.wantPaperTrail)
			}
		})
	}
}

func TestGateHandler_TokenValidates(t *testing.T) {
	django := mockDjango(t)
	defer django.Close()
	cfg := newTestConfig(t, django.URL)
	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	resp, err := http.Get(server.URL + "/gate?type=reconciliation")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	var out struct {
		State struct {
			SessionType    string `json:"session_type"`
			Token          string `json:"token"`
			TS             int64  `json:"ts"`
			TotalOpenCount int    `json:"total_open_count"`
		} `json:"state"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatal(err)
	}

	// Recompute the token exactly as the Python hook will.
	msg := fmt.Sprintf("%s|%d|%d", out.State.SessionType, out.State.TS, out.State.TotalOpenCount)
	mac := hmac.New(sha256.New, []byte(cfg.Secret))
	mac.Write([]byte(msg))
	want := hex.EncodeToString(mac.Sum(nil))[:16]

	if out.State.Token != want {
		t.Errorf("token = %q, want %q (msg=%q)", out.State.Token, want, msg)
	}
	if out.State.TS != fixedClock().Unix()/60 {
		t.Errorf("ts = %d, want unix-minute %d", out.State.TS, fixedClock().Unix()/60)
	}
}

func TestGateHandler_WritesStateFile(t *testing.T) {
	django := mockDjango(t)
	defer django.Close()
	cfg := newTestConfig(t, django.URL)
	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	resp, err := http.Get(server.URL + "/gate?type=reconciliation")
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()

	data, err := os.ReadFile(cfg.StatePath)
	if err != nil {
		t.Fatalf("state file not written: %v", err)
	}
	var state map[string]any
	if err := json.Unmarshal(data, &state); err != nil {
		t.Fatalf("state file is not valid JSON: %v", err)
	}
	for _, key := range []string{"session_type", "layer2_autoissues", "layer2_paper_trail", "token", "ts", "total_open_count", "generated_at"} {
		if _, ok := state[key]; !ok {
			t.Errorf("state file missing key %q", key)
		}
	}
}

func TestGateHandler_UnknownSessionType(t *testing.T) {
	django := mockDjango(t)
	defer django.Close()
	cfg := newTestConfig(t, django.URL)
	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	resp, err := http.Get(server.URL + "/gate?type=bogus")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("unknown session type status = %d, want 400", resp.StatusCode)
	}
}

func TestGateHandler_BackendDown_ReturnsBadGateway(t *testing.T) {
	cfg := newTestConfig(t, "http://127.0.0.1:1") // nothing is listening here
	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	resp, err := http.Get(server.URL + "/gate?type=reconciliation")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusBadGateway {
		t.Fatalf("backend-down status = %d, want 502", resp.StatusCode)
	}
}

// TestGateHandler_CachesDjangoButResignsToken proves the in-memory cache skips
// the Django round-trip on a repeat request (same session type + areas) within
// the TTL, while still re-signing a fresh HMAC token on every request, and that
// the cache refreshes from Django after the TTL expires.
func TestGateHandler_CachesDjangoButResignsToken(t *testing.T) {
	var djangoCalls int32
	django := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&djangoCalls, 1)
		body := map[string]any{
			"markers": map[string]string{
				"sticky": "[STICKY 1 READ: x]", "registry": "[REGISTRY READ: x]",
				"paper_trail": "[PAPER TRAIL READ: x]", "snapshots": "[SNAPSHOTS READ: x]",
				"lessons": "[LESSONS BEFORE START: x]", "tdd_preflight": "[TDD PREFLIGHT: x]",
			},
			"total_open_count": 142,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(body)
	}))
	defer django.Close()

	// Controllable clock starting 50s into a minute so a +20s step crosses the
	// minute boundary (changing the token timestamp) while staying inside the TTL.
	clock := time.Date(2026, 5, 28, 12, 0, 50, 0, time.UTC)
	cfg := newTestConfig(t, django.URL)
	cfg.Now = func() time.Time { return clock }

	server := httptest.NewServer(Handler(cfg))
	defer server.Close()

	getToken := func() string {
		resp, err := http.Get(server.URL + "/gate?type=reconciliation&area=backend/apps/core")
		if err != nil {
			t.Fatal(err)
		}
		defer func() { _ = resp.Body.Close() }()
		var out struct {
			State struct {
				Token string `json:"token"`
			} `json:"state"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
			t.Fatal(err)
		}
		return out.State.Token
	}

	// 1) Cache miss: Django is queried once.
	tok1 := getToken()
	if got := atomic.LoadInt32(&djangoCalls); got != 1 {
		t.Fatalf("after first request: django calls = %d, want 1", got)
	}

	// 2) Within the TTL but a minute later: cache HIT (Django not re-queried) yet
	//    the token is RE-SIGNED because the unix-minute timestamp changed.
	clock = clock.Add(20 * time.Second) // 12:01:10 — crosses the minute, inside TTL
	tok2 := getToken()
	if got := atomic.LoadInt32(&djangoCalls); got != 1 {
		t.Fatalf("cache hit should not re-query django: calls = %d, want 1", got)
	}
	if tok2 == tok1 {
		t.Fatalf("token must be re-signed each request even on a cache hit (tok1==tok2==%q)", tok1)
	}

	// 3) After the TTL expires, the cache is refreshed from Django again.
	clock = clock.Add(90 * time.Second) // well past the cache TTL
	_ = getToken()
	if got := atomic.LoadInt32(&djangoCalls); got != 2 {
		t.Fatalf("after TTL expiry: django calls = %d, want 2", got)
	}
}
