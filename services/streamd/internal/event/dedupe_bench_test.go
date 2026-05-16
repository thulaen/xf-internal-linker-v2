package event

import (
	"fmt"
	"testing"
)

func BenchmarkDedupeKey(b *testing.B) {
	cases := []struct {
		name    string
		payload map[string]any
	}{
		{
			name: "small",
			payload: map[string]any{
				"event":   "post_updated",
				"post_id": 42,
			},
		},
		{
			name: "medium",
			payload: map[string]any{
				"event":   "post_updated",
				"post_id": 42,
				"title":   "Example title",
				"tags":    []any{"alpha", "beta", "gamma"},
			},
		},
		{
			name:    "large",
			payload: largeBenchmarkPayload(),
		},
	}

	for _, item := range cases {
		b.Run(item.name, func(b *testing.B) {
			for b.Loop() {
				if _, err := DedupeKey("wp", "post_updated", item.payload); err != nil {
					b.Fatalf("dedupe key: %v", err)
				}
			}
		})
	}
}

func largeBenchmarkPayload() map[string]any {
	payload := make(map[string]any, 32)
	for index := range 32 {
		payload[fmt.Sprintf("field_%02d", index)] = fmt.Sprintf("value_%02d", index)
	}
	payload["tags"] = []any{"alpha", "beta", "gamma", "delta", "epsilon"}
	return payload
}
